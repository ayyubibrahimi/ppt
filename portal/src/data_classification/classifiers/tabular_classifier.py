"""
Tabular Classifier - Classifies CSV/XLSX files against FOIA requests
"""

import logging
import os
from typing import Dict, Any, Optional
import pandas as pd
from jinja2 import Template

from data_classification.base_classifier import BaseClassifier
from data_classification.pydantic_models import (
    ClassificationResult,
    SheetClassification,
    RequestContext,
    DocumentContext
)
from data_classification.prompts import (
    get_tabular_classification_prompt,
    get_sheet_classification_prompt,
    get_sheet_orchestrator_prompt
)
from data_classification.llm_models import run_structured_inference

logger = logging.getLogger(__name__)


class TabularClassifier(BaseClassifier):
    """
    Classifier for CSV/XLSX tabular data files.

    Performs exploratory data analysis (EDA) to extract table structure,
    then uses LLM to compare against FOIA request requirements.
    """

    def classify(
        self,
        document_data: Dict[str, Any],
        request_context: RequestContext,
        document_context: DocumentContext
    ) -> ClassificationResult:
        """
        Classify if a tabular data file matches the FOIA request.

        Args:
            document_data: Dict with:
                - 'file_path': Local file path (checked first)
                - 'google_drive_file_id': Google Drive file ID (fallback if local missing)
                - 'download_id': Download record ID (for temp file naming)
            request_context: Context about the FOIA request
            document_context: Metadata about the document

        Returns:
            ClassificationResult with match decision and explanation

        Raises:
            ValueError: If document_data is missing required keys or file not found
            RuntimeError: If classification fails
        """
        logger.info(f"🏷️  Classifying tabular document: {document_context.document_title}")

        # Validate input - file_path is required
        self._validate_document_data(document_data, ['file_path'])

        file_path = document_data['file_path']

        # Check if local file exists, if not try to download from Google Drive
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ Local file not found: {file_path}")

            # Try to download from Google Drive
            google_drive_file_id = document_data.get('google_drive_file_id')

            if google_drive_file_id:
                logger.info(f"📥 Attempting to download from Google Drive: {google_drive_file_id}")
                file_path = self._download_from_google_drive(
                    google_drive_file_id,
                    document_context.document_title,
                    document_data.get('download_id', 'temp')
                )
            else:
                raise ValueError(
                    f"File not found locally and no Google Drive file ID available. "
                    f"Local path: {file_path}"
                )

        try:
            # Check if this is a multi-sheet Excel file
            if document_context.file_extension.lower() in ['.xlsx', '.xls']:
                excel_file = pd.ExcelFile(file_path)
                sheet_names = excel_file.sheet_names

                if len(sheet_names) > 1:
                    # Multi-sheet Excel: Use hierarchical classification
                    logger.info(f"📊 Multi-sheet Excel detected: {len(sheet_names)} sheets")
                    return self._classify_multisheet_excel(
                        file_path=file_path,
                        sheet_names=sheet_names,
                        request_context=request_context
                    )

            # Single-sheet or CSV: Use traditional single-document classification
            logger.info(f"📊 Single-sheet document, using traditional classification")

            # Perform EDA
            eda_result = self._perform_eda(
                file_path=file_path,
                file_extension=document_context.file_extension
            )

            logger.info(
                f"📊 EDA complete: {eda_result['num_rows']} rows, "
                f"{eda_result['num_columns']} columns"
            )

            # Build timeline summary
            timeline_summary = self._build_timeline_summary(request_context.timeline_events)

            # Build prompt
            prompt = self._build_classification_prompt(
                request_text=request_context.request_text,
                timeline_summary=timeline_summary,
                eda_result=eda_result,
                file_extension=document_context.file_extension
            )

            logger.info(f"🤖 Sending classification request to LLM")

            # Call LLM with structured inference
            result = run_structured_inference(
                prompt=prompt,
                response_model=ClassificationResult,
                max_tokens=1000,
                temperature=0.1
            )

            logger.info(
                f"✅ Classification complete: Match={result.records_match_request} "
                f"for {document_context.document_title}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Tabular classification failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Tabular classification failed: {str(e)}")

    def _classify_multisheet_excel(
        self,
        file_path: str,
        sheet_names: list,
        request_context: RequestContext
    ) -> ClassificationResult:
        """
        Classify a multi-sheet Excel file using hierarchical approach.

        Step 1: Classify each sheet individually
        Step 2: Orchestrate final decision based on sheet results

        Args:
            file_path: Path to Excel file
            sheet_names: List of sheet names in the file
            request_context: Context about the FOIA request

        Returns:
            ClassificationResult with overall decision

        Raises:
            RuntimeError: If classification fails
        """
        logger.info(f"🔍 Starting hierarchical classification for {len(sheet_names)} sheets")

        sheet_results = []

        # Step 1: Classify each sheet
        for sheet_name in sheet_names:
            try:
                logger.info(f"📄 Analyzing sheet: {sheet_name}")

                # Read sheet data
                sheet_df = pd.read_excel(file_path, sheet_name=sheet_name)

                # Classify this specific sheet
                sheet_result = self._classify_single_sheet(
                    sheet_name=sheet_name,
                    sheet_df=sheet_df,
                    request_context=request_context
                )

                sheet_results.append(sheet_result)

            except Exception as e:
                logger.error(f"❌ Failed to classify sheet '{sheet_name}': {str(e)}", exc_info=True)
                # Add error result for this sheet
                sheet_results.append(SheetClassification(
                    sheet_name=sheet_name,
                    contains_relevant_data=False,
                    matches_request_requirements=False,
                    summary=f"Failed to analyze: {str(e)}",
                    reasoning="Classification error"
                ))

        # Step 2: Orchestrate final decision
        logger.info(f"🎭 Orchestrating final decision from {len(sheet_results)} sheet results")

        final_result = self._orchestrate_sheet_classifications(
            sheet_results=sheet_results,
            request_context=request_context
        )

        # Log summary
        fully_matching_sheets = [s.sheet_name for s in sheet_results if s.matches_request_requirements]
        partially_matching_sheets = [
            s.sheet_name for s in sheet_results
            if s.contains_relevant_data and not s.matches_request_requirements
        ]

        if fully_matching_sheets:
            logger.info(f"✅ Sheets fully matching request: {', '.join(fully_matching_sheets)}")
        if partially_matching_sheets:
            logger.info(f"⚠️ Sheets with relevant data but missing fields: {', '.join(partially_matching_sheets)}")
        if not fully_matching_sheets and not partially_matching_sheets:
            logger.info(f"❌ No sheets contain relevant data")

        return final_result

    def _perform_eda(self, file_path: str, file_extension: str) -> Dict[str, Any]:
        """
        Perform exploratory data analysis on a CSV/XLSX file.

        Args:
            file_path: Path to the data file
            file_extension: File extension (.csv or .xlsx)

        Returns:
            Dict with EDA results (columns, types, samples, etc.)

        Raises:
            ValueError: If file cannot be loaded
        """
        logger.info(f"📊 Starting EDA for {os.path.basename(file_path)}")

        try:
            # Load file based on extension
            if file_extension.lower() == '.csv':
                df = pd.read_csv(file_path)
            elif file_extension.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_extension}")

            # Extract basic info
            num_rows, num_columns = df.shape
            columns = df.columns.tolist()

            # Data types
            data_types = {col: str(dtype) for col, dtype in df.dtypes.items()}

            # Sample data (first 5 rows, formatted)
            sample_data = df.head(5).to_dict(orient='records')

            # Format sample for readability
            sample_formatted = self._format_sample_data(sample_data, max_samples=5)

            # Statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            statistics = {}
            if numeric_cols:
                stats_df = df[numeric_cols].describe()
                statistics = stats_df.to_dict()

            # Missing data
            missing_data = df.isnull().sum().to_dict()

            # Unique value counts for categorical columns (up to 10 columns)
            categorical_cols = df.select_dtypes(include=['object']).columns.tolist()[:10]
            unique_counts = {col: int(df[col].nunique()) for col in categorical_cols}

            eda_result = {
                'num_rows': num_rows,
                'num_columns': num_columns,
                'columns': columns,
                'data_types': data_types,
                'sample_data': sample_formatted,
                'statistics': statistics,
                'missing_data': missing_data,
                'unique_counts': unique_counts,
                'numeric_columns': numeric_cols,
                'categorical_columns': categorical_cols
            }

            logger.info(
                f"✅ EDA complete: {num_rows} rows, {num_columns} columns, "
                f"{len(numeric_cols)} numeric, {len(categorical_cols)} categorical"
            )

            return eda_result

        except Exception as e:
            logger.error(f"❌ EDA failed: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to analyze table: {str(e)}")

    def _format_sample_data(
        self,
        sample_data: list,
        max_samples: int = 5
    ) -> str:
        """
        Format sample data for inclusion in prompt.

        Args:
            sample_data: List of row dicts
            max_samples: Maximum number of samples to include

        Returns:
            Formatted string representation of sample data
        """
        if not sample_data:
            return "No sample data available"

        # Limit number of samples
        sample_data = sample_data[:max_samples]

        # Format as readable text
        formatted_lines = []
        for i, row in enumerate(sample_data, 1):
            formatted_lines.append(f"Row {i}:")
            for key, value in row.items():
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                formatted_lines.append(f"  {key}: {value_str}")
            formatted_lines.append("")  # Blank line between rows

        return "\n".join(formatted_lines)

    def _build_classification_prompt(
        self,
        request_text: str,
        timeline_summary: str,
        eda_result: Dict[str, Any],
        file_extension: str
    ) -> str:
        """
        Build the classification prompt for the LLM.

        Args:
            request_text: Original FOIA request
            timeline_summary: Formatted timeline of correspondence
            eda_result: EDA analysis results
            file_extension: File extension (.csv or .xlsx)

        Returns:
            Complete prompt string
        """
        template_str = get_tabular_classification_prompt()
        template = Template(template_str)

        prompt = template.render(
            request_text=request_text,
            timeline_summary=timeline_summary,
            file_type=file_extension,
            num_rows=eda_result['num_rows'],
            num_columns=eda_result['num_columns'],
            columns=", ".join(str(col) for col in eda_result['columns']),
            data_types=eda_result['data_types'],
            sample_data=eda_result['sample_data']
        )

        return prompt

    def _classify_single_sheet(
        self,
        sheet_name: str,
        sheet_df: pd.DataFrame,
        request_context: RequestContext
    ) -> SheetClassification:
        """
        Classify a single sheet from a multi-sheet Excel file.

        Args:
            sheet_name: Name of the sheet
            sheet_df: DataFrame containing the sheet data
            request_context: Context about the FOIA request

        Returns:
            SheetClassification with analysis of this specific sheet

        Raises:
            RuntimeError: If classification fails
        """
        try:
            logger.info(f"📄 Classifying sheet: {sheet_name}")

            # Extract basic info
            num_rows, num_columns = sheet_df.shape
            columns = sheet_df.columns.tolist()

            # Sample data (first 3 rows for quick analysis)
            sample_data = sheet_df.head(3).to_dict(orient='records')
            sample_formatted = self._format_sample_data(sample_data, max_samples=3)

            # Build prompt
            template_str = get_sheet_classification_prompt()
            template = Template(template_str)

            prompt = template.render(
                request_text=request_context.request_text,
                sheet_name=sheet_name,
                num_rows=num_rows,
                num_columns=num_columns,
                columns=", ".join(str(col) for col in columns),
                sample_data=sample_formatted
            )

            # Call LLM with structured inference
            result = run_structured_inference(
                prompt=prompt,
                response_model=SheetClassification,
                max_tokens=500,
                temperature=0.1
            )

            logger.info(
                f"✅ Sheet '{sheet_name}': relevant={result.contains_relevant_data}, "
                f"matches_requirements={result.matches_request_requirements}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Failed to classify sheet '{sheet_name}': {str(e)}", exc_info=True)
            # Return a safe default classification on error
            return SheetClassification(
                sheet_name=sheet_name,
                contains_relevant_data=False,
                matches_request_requirements=False,
                summary=f"Failed to analyze sheet: {str(e)}",
                reasoning="Classification error occurred"
            )

    def _orchestrate_sheet_classifications(
        self,
        sheet_results: list,
        request_context: RequestContext
    ) -> ClassificationResult:
        """
        Orchestrate final classification based on individual sheet results.

        Args:
            sheet_results: List of SheetClassification objects
            request_context: Context about the FOIA request

        Returns:
            ClassificationResult with overall decision

        Raises:
            RuntimeError: If orchestration fails
        """
        try:
            logger.info(f"🎭 Orchestrating classification for {len(sheet_results)} sheets")

            # Build prompt
            template_str = get_sheet_orchestrator_prompt()
            template = Template(template_str)

            prompt = template.render(
                request_text=request_context.request_text,
                sheet_results=sheet_results
            )

            # Call LLM with structured inference
            result = run_structured_inference(
                prompt=prompt,
                response_model=ClassificationResult,
                max_tokens=1000,
                temperature=0.1
            )

            logger.info(
                f"✅ Orchestration complete: Match={result.records_match_request}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Orchestration failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Sheet orchestration failed: {str(e)}")

    def _download_from_google_drive(
        self,
        google_drive_file_id: str,
        filename: str,
        download_id: str
    ) -> str:
        """
        Download file from Google Drive to temp directory.

        Args:
            google_drive_file_id: Google Drive file ID
            filename: Original filename
            download_id: Download record ID for temp file naming

        Returns:
            Path to downloaded file

        Raises:
            RuntimeError: If download fails
        """
        try:
            from google_drive_manager import GoogleDriveManager
            import tempfile

            # Create temp directory for classification
            temp_dir = tempfile.mkdtemp(prefix='classification_')
            temp_file_path = os.path.join(temp_dir, filename)

            logger.info(f"📥 Downloading {filename} from Google Drive to {temp_file_path}")

            # Initialize Drive manager and download
            # Use self.db if available, otherwise create new instance
            if not self.db:
                from supabase_integration import SupabaseIntegration
                logger.warning("⚠️ No database instance available, creating new one")
                db_instance = SupabaseIntegration()
            else:
                db_instance = self.db

            # Get user_id from download record to initialize Google Drive
            doc_record = db_instance.get_document_with_data(download_id)
            if not doc_record or not doc_record.get('user_id'):
                raise RuntimeError(f"Could not get user_id for download {download_id}")

            user_id = doc_record['user_id']

            # Initialize Google Drive manager for user
            drive_manager = GoogleDriveManager(supabase_db=db_instance)
            if not drive_manager.initialize_for_user(user_id):
                raise RuntimeError(f"Failed to initialize Google Drive for user {user_id}")

            # Download file from Google Drive
            success = drive_manager.download_file(google_drive_file_id, temp_file_path)

            if not success:
                raise RuntimeError(f"Failed to download file from Google Drive: {google_drive_file_id}")

            logger.info(f"✅ Successfully downloaded {filename} for classification")

            return temp_file_path

        except Exception as e:
            logger.error(f"❌ Google Drive download failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to download from Google Drive: {str(e)}")
