'use client'

import { useState, useEffect } from 'react'
import {
  FileText,
  Clock,
  AlertTriangle,
  Calendar,
  Globe,
  DollarSign,
  MessageSquare,
  RefreshCw,
  Activity,
  Send,
  FileCheck,
  TrendingUp,
  Download
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import styles from './RequestDetailPage.module.scss'
import { RequestDetailData, UploadedDocument } from '@/types/requests'

interface RequestDetailPageProps {
  requestDetailData: RequestDetailData | null
  isLoading: boolean
  onSwitchToMessages: () => void
  onRefresh: () => void
}

export default function RequestDetailPage({
  requestDetailData,
  isLoading,
  onSwitchToMessages,
  onRefresh
}: RequestDetailPageProps) {
  const [activeSection, setActiveSection] = useState<string>('overview')
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([])
  const [documentsLoading, setDocumentsLoading] = useState(false)
  const [documentsError, setDocumentsError] = useState<string | null>(null)

  // Three-panel state
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState<'all' | 'matches' | 'no-matches' | 'pending'>('all')
  const [isRequestTextExpanded, setIsRequestTextExpanded] = useState(false)

  // Fetch uploaded documents for the request
  const fetchUploadedDocuments = async (requestId: string) => {
    setDocumentsLoading(true)
    setDocumentsError(null)

    try {
      const response = await fetch(`/api/documents/${requestId}`)

      if (!response.ok) {
        throw new Error('Failed to fetch documents')
      }

      const data = await response.json()
      setUploadedDocuments(data.documents || [])
    } catch (err) {
      console.error('Error fetching documents:', err)
      setDocumentsError('Failed to load documents')
    } finally {
      setDocumentsLoading(false)
    }
  }

  // Fetch documents when request changes
  useEffect(() => {
    if (requestDetailData?.request?.id) {
      fetchUploadedDocuments(requestDetailData.request.id)
    }
  }, [requestDetailData?.request?.id])

  // Select first document when documents load
  useEffect(() => {
    if (uploadedDocuments.length > 0 && !selectedDocumentId) {
      setSelectedDocumentId(uploadedDocuments[0].id)
    }
  }, [uploadedDocuments, selectedDocumentId])

  // Filter and search documents
  const filteredDocuments = uploadedDocuments.filter(doc => {
    // Apply search filter
    if (searchQuery && !doc.document_title.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false
    }

    // Apply status filter
    if (filterStatus === 'matches' && !doc.records_match_request) return false
    if (filterStatus === 'no-matches' && doc.records_match_request !== false) return false
    if (filterStatus === 'pending' && doc.classification_status !== 'pending') return false

    return true
  })

  // Get selected document
  const selectedDocument = uploadedDocuments.find(doc => doc.id === selectedDocumentId)

  // Navigate documents with keyboard
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedDocumentId || filteredDocuments.length === 0) return

      const currentIndex = filteredDocuments.findIndex(doc => doc.id === selectedDocumentId)

      if (e.key === 'ArrowDown' && currentIndex < filteredDocuments.length - 1) {
        e.preventDefault()
        setSelectedDocumentId(filteredDocuments[currentIndex + 1].id)
      } else if (e.key === 'ArrowUp' && currentIndex > 0) {
        e.preventDefault()
        setSelectedDocumentId(filteredDocuments[currentIndex - 1].id)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedDocumentId, filteredDocuments])

  // Calculate classification stats
  const classificationStats = {
    total: uploadedDocuments.length,
    matches: uploadedDocuments.filter(d => d.records_match_request === true).length,
    noMatches: uploadedDocuments.filter(d => d.records_match_request === false).length,
    pending: uploadedDocuments.filter(d => d.classification_status === 'pending' || !d.classification_status).length
  }

  // Helper functions for styling
  const getPriorityColor = (priority: string) => {
    switch (priority?.toLowerCase()) {
      case 'high':
        return 'priorityHigh'
      case 'medium':
        return 'priorityMedium'
      case 'low':
        return 'priorityLow'
      default:
        return 'priorityDefault'
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'open':
        return 'statusOpen'
      case 'in_progress':
        return 'statusProgress'
      case 'pending_payment':
        return 'statusPending'
      case 'completed':
        return 'statusCompleted'
      default:
        return 'statusDefault'
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity?.toLowerCase()) {
      case 'high':
        return 'severityHigh'
      case 'medium':
        return 'severityMedium'
      case 'low':
        return 'severityLow'
      default:
        return 'severityDefault'
    }
  }

  const getDraftStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'sent':
        return 'draftSent'
      case 'approved':
        return 'draftApproved'
      case 'drafted':
        return 'draftDrafted'
      case 'rejected':
        return 'draftRejected'
      case 'skipped':
        return 'draftSkipped'
      default:
        return 'draftDefault'
    }
  }

  const formatTimelineEvent = (event: string | { description?: string; message?: string; event?: string } | unknown) => {
    if (typeof event === 'string') {
      return event
    }
    if (event && typeof event === 'object' && event !== null) {
      const eventObj = event as { description?: string; message?: string; event?: string }
      return eventObj.description || eventObj.message || eventObj.event || JSON.stringify(event)
    }
    return 'Unknown event'
  }

  const getTimelineEventType = (event: string | { description?: string; message?: string; event?: string } | unknown) => {
    const eventStr = formatTimelineEvent(event).toLowerCase()
    if (eventStr.includes('submitted') || eventStr.includes('received')) return 'submitted'
    if (eventStr.includes('payment') || eventStr.includes('fee')) return 'payment'
    if (eventStr.includes('document') || eventStr.includes('file')) return 'document'
    if (eventStr.includes('status') || eventStr.includes('updated')) return 'status'
    if (eventStr.includes('message') || eventStr.includes('email')) return 'message'
    return 'general'
  }

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'submitted':
        return <Send className={styles.timelineIcon} />
      case 'payment':
        return <DollarSign className={styles.timelineIcon} />
      case 'document':
        return <FileCheck className={styles.timelineIcon} />
      case 'status':
        return <TrendingUp className={styles.timelineIcon} />
      case 'message':
        return <MessageSquare className={styles.timelineIcon} />
      default:
        return <Activity className={styles.timelineIcon} />
    }
  }

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <div className={styles.loadingSpinner}></div>
          <span className={styles.loadingText}>Loading request details...</span>
        </div>
      </div>
    )
  }

  if (!requestDetailData) {
    return (
      <div className={styles.container}>
        <div className={styles.emptyState}>
          <FileText className={styles.emptyIcon} />
          <h3 className={styles.emptyTitle}>No Request Selected</h3>
          <p className={styles.emptyText}>
            Select a request to view comprehensive details and analysis.
          </p>
        </div>
      </div>
    )
  }

  const { request, changes, messageHistory, timelineEvents, documents, payments, staffContact, deadlines } = requestDetailData

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <FileText className={styles.icon} />
            </div>
            <div className={styles.headerText}>
              <h1 className={styles.title}>Request #{request.request_number}</h1>
              <p className={styles.subtitle}>{request.portal_name}</p>
            </div>
          </div>
          
          <div className={styles.headerRight}>
            <div className={styles.headerBadges}>
              <Badge className={styles[getPriorityColor(request.agent_attention_priority)]}>
                {request.agent_attention_priority?.toUpperCase() || 'NORMAL'} PRIORITY
              </Badge>
              <Badge className={styles[getStatusColor(request.current_status)]}>
                {request.current_status?.replace('_', ' ').toUpperCase()}
              </Badge>
              {request.action_required && (
                <Badge className={styles.actionRequired}>
                  ACTION REQUIRED
                </Badge>
              )}
            </div>
            
            <div className={styles.headerActions}>
              <Button
                variant="outline"
                onClick={onRefresh}
                className={styles.refreshButton}
              >
                <RefreshCw className={styles.actionIcon} />
                Refresh
              </Button>
              <Button
                onClick={onSwitchToMessages}
                className={styles.messagesButton}
              >
                <MessageSquare className={styles.actionIcon} />
                Manage Messages
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Three-Panel Layout */}
      <div className={styles.threePanelContainer}>
        {/* PANEL 1: Request Context (Left) */}
        <div className={styles.contextPanel}>
          {/* Attention Required */}
          {request.agent_attention_needed && (
            <Card className={styles.attentionCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <AlertTriangle className={styles.cardIcon} />
                  Attention Required
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                <div className={styles.attentionContent}>
                  <div className={styles.attentionReason}>
                    {request.agent_attention_reason}
                  </div>
                  <div className={styles.attentionMeta}>
                    <span className={styles.attentionPriority}>
                      Priority: {request.agent_attention_priority?.toUpperCase() || 'NORMAL'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Request Summary */}
          <Card className={styles.summaryCard}>
            <CardHeader className={styles.cardHeader}>
              <CardTitle className={styles.cardTitle}>
                <Globe className={styles.cardIcon} />
                Request Summary
              </CardTitle>
            </CardHeader>
            <CardContent className={styles.cardContent}>
              <div className={styles.summaryDetails}>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Portal:</span>
                  <span className={styles.detailValue}>{request.portal_name}</span>
                </div>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Status:</span>
                  <span className={styles.detailValue}>{request.current_status?.replace('_', ' ')}</span>
                </div>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Created:</span>
                  <span className={styles.detailValue}>
                    {new Date(request.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Last Updated:</span>
                  <span className={styles.detailValue}>
                    {new Date(request.updated_at).toLocaleDateString()}
                  </span>
                </div>
                {staffContact && (
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Staff Contact:</span>
                    <span className={styles.detailValue}>{staffContact}</span>
                  </div>
                )}

                {/* Collapsible Request Text */}
                {request.request_text && (
                  <div className={styles.requestTextSection}>
                    <button
                      className={styles.requestTextToggle}
                      onClick={() => setIsRequestTextExpanded(!isRequestTextExpanded)}
                    >
                      <span className={styles.detailLabel}>Original Request:</span>
                      <span className={styles.toggleIcon}>{isRequestTextExpanded ? '▼' : '▶'}</span>
                    </button>
                    {isRequestTextExpanded && (
                      <div className={styles.requestTextValue}>
                        {request.request_text}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Timeline Events */}
          <Card className={styles.timelineCard}>
            <CardHeader className={styles.cardHeader}>
              <CardTitle className={styles.cardTitle}>
                <Clock className={styles.cardIcon} />
                Timeline Events ({timelineEvents.length})
              </CardTitle>
            </CardHeader>
            <CardContent className={styles.cardContent}>
              {timelineEvents.length > 0 ? (
                <div className={styles.timeline}>
                  {timelineEvents.map((event, index) => {
                    const eventType = getTimelineEventType(event)
                    return (
                      <div key={index} className={styles.timelineItem}>
                        <div className={styles.timelineMarker}>
                          {getEventIcon(eventType)}
                        </div>
                        <div className={styles.timelineContent}>
                          <div className={styles.timelineText}>
                            {formatTimelineEvent(event)}
                          </div>
                          <div className={styles.timelineDate}>
                            Event #{index + 1}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className={styles.emptySection}>
                  <Clock className={styles.emptySectionIcon} />
                  <p className={styles.emptySectionText}>No timeline events recorded</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Payments & Deadlines */}
          <Card className={styles.resourcesCard}>
            <CardHeader className={styles.cardHeader}>
              <CardTitle className={styles.cardTitle}>
                <DollarSign className={styles.cardIcon} />
                Payments & Deadlines
              </CardTitle>
            </CardHeader>
            <CardContent className={styles.cardContent}>
              <div className={styles.resourcesContent}>
                <div className={styles.resourceSection}>
                  <h4 className={styles.resourceTitle}>
                    <DollarSign className={styles.resourceIcon} />
                    Payments ({payments.length})
                  </h4>
                  {payments.length > 0 ? (
                    <div className={styles.resourceList}>
                      {payments.map((payment, index) => (
                        <div key={index} className={styles.resourceItem}>
                          {typeof payment === 'string' ? payment : JSON.stringify(payment)}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className={styles.resourceEmpty}>No outstanding payments</p>
                  )}
                </div>

                {deadlines.length > 0 && (
                  <div className={styles.resourceSection}>
                    <h4 className={styles.resourceTitle}>
                      <Calendar className={styles.resourceIcon} />
                      Deadlines ({deadlines.length})
                    </h4>
                    <div className={styles.resourceList}>
                      {deadlines.map((deadline, index) => (
                        <div key={index} className={styles.resourceItem}>
                          {deadline}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* PANEL 2: Documents List (Middle) */}
        <div className={styles.documentsListPanel}>
          <Card className={styles.documentsListCard}>
            <CardHeader className={styles.cardHeader}>
              <CardTitle className={styles.cardTitle}>
                <FileText className={styles.cardIcon} />
                Documents ({filteredDocuments.length})
              </CardTitle>
            </CardHeader>
            <CardContent className={styles.cardContent}>
              {/* Classification Stats */}
              {uploadedDocuments.length > 0 && (
                <div className={styles.statsBar}>
                  <div className={styles.statBadge} style={{ backgroundColor: 'rgba(5, 150, 105, 0.2)', color: 'var(--success)' }}>
                    ✓ {classificationStats.matches} Match
                  </div>
                  <div className={styles.statBadge} style={{ backgroundColor: 'rgba(220, 38, 38, 0.2)', color: 'var(--error)' }}>
                    ✗ {classificationStats.noMatches} No Match
                  </div>
                  <div className={styles.statBadge} style={{ backgroundColor: 'rgba(100, 116, 139, 0.2)', color: 'var(--text-muted)' }}>
                    {classificationStats.pending} Pending Download
                  </div>
                </div>
              )}

              {/* Search and Filter */}
              {uploadedDocuments.length > 0 && (
                <div className={styles.searchFilterBar}>
                  <input
                    type="text"
                    placeholder="Search documents..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className={styles.searchInput}
                  />
                  <select
                      value={filterStatus}
                      onChange={(e) => setFilterStatus(e.target.value as 'all' | 'matches' | 'no-matches' | 'pending')}
                      className={styles.filterSelect}
                    >
                    <option value="all">All</option>
                    <option value="matches">Matches</option>
                    <option value="no-matches">No Matches</option>
                    <option value="pending">Pending</option>
                  </select>
                </div>
              )}

              {/* Documents List */}
              {documentsLoading ? (
                <div className={styles.emptySection}>
                  <div className={styles.loadingSpinner}></div>
                  <p className={styles.emptySectionText}>Loading documents...</p>
                </div>
              ) : documentsError ? (
                <div className={styles.emptySection}>
                  <FileText className={styles.emptySectionIcon} />
                  <p className={styles.emptySectionText} style={{ color: '#dc2626' }}>
                    {documentsError}
                  </p>
                </div>
              ) : filteredDocuments.length > 0 ? (
                <div className={styles.documentsList}>
                  {filteredDocuments.map((doc) => (
                    <div
                      key={doc.id}
                      className={`${styles.documentListItem} ${selectedDocumentId === doc.id ? styles.documentListItemSelected : ''}`}
                      onClick={() => setSelectedDocumentId(doc.id)}
                    >
                      <div className={styles.documentListItemIcon}>
                        {doc.records_match_request === true && <span className={styles.iconMatch}>✓</span>}
                        {doc.records_match_request === false && <span className={styles.iconNoMatch}>✗</span>}
                        {!doc.records_match_request && doc.records_match_request !== false && <span className={styles.iconPending}>⏳</span>}
                      </div>
                      <div className={styles.documentListItemContent}>
                        <div className={styles.documentListItemTitle}>{doc.document_title}</div>
                        <div className={styles.documentListItemMeta}>
                          {doc.num_pages && (
                            <div className={styles.metaRow}>
                              <span className={styles.metaLabel}>Number of pages:</span> {doc.num_pages}
                            </div>
                          )}
                          {doc.classification_status === 'completed' && (
                            <div className={doc.records_match_request ? styles.matchStatus : styles.noMatchStatus}>
                              {doc.records_match_request
                                ? 'Records received match what you requested'
                                : 'Released records do not appear to match your original request'}
                            </div>
                          )}
                          {doc.classification_status === 'pending' && (
                            <div className={styles.pendingStatus}>
                              Classification pending review
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.emptySection}>
                  <FileText className={styles.emptySectionIcon} />
                  <p className={styles.emptySectionText}>
                    {uploadedDocuments.length === 0 ? 'No documents released yet' : 'No documents match filters'}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* PANEL 3: Document Detail (Right) */}
        <div className={styles.documentDetailPanel}>
          <Card className={styles.documentDetailCard}>
            {selectedDocument ? (
              <>
                <CardHeader className={styles.cardHeader}>
                  <CardTitle className={styles.cardTitle}>
                    <FileText className={styles.cardIcon} />
                    {selectedDocument.document_title}
                  </CardTitle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.open(selectedDocument.google_drive_web_link, '_blank')}
                    className={styles.downloadButton}
                  >
                    <Download className={styles.buttonIcon} />
                    Download
                  </Button>
                </CardHeader>
                <CardContent className={styles.cardContent}>
                  {/* Classification Section */}
                  {selectedDocument.classification_status === 'completed' && (
                    <div className={styles.classificationSection}>
                      <h4 className={styles.sectionTitle}>Classification Result</h4>
                      <div className={selectedDocument.records_match_request ? styles.matchStatusDetail : styles.noMatchStatusDetail}>
                        <div className={styles.statusIcon}>
                          {selectedDocument.records_match_request ? '✓' : '✗'}
                        </div>
                        <div className={styles.statusText}>
                          {selectedDocument.records_match_request
                            ? 'Records received match what you requested'
                            : 'Released records do not appear to match your original request'}
                        </div>
                      </div>
                      {selectedDocument.classification_explanation && (
                        <div className={styles.classificationExplanation}>
                          <strong>Explanation:</strong> {selectedDocument.classification_explanation}
                        </div>
                      )}
                    </div>
                  )}

                  {selectedDocument.classification_status === 'pending' && (
                    <div className={styles.classificationSection}>
                      <h4 className={styles.sectionTitle}>Classification Result</h4>
                      <div className={styles.pendingStatusDetail}>
                        <div className={styles.statusIcon}>⏳</div>
                        <div className={styles.statusText}>Classification pending review</div>
                      </div>
                    </div>
                  )}

                  {/* Summary Section */}
                  {selectedDocument.document_data?.summary?.summary_text ? (
                    <div className={styles.summarySection}>
                      <h4 className={styles.sectionTitle}>Summary</h4>
                      <div className={styles.summaryTextDetail}>
                        {selectedDocument.document_data.summary.summary_text}
                      </div>
                    </div>
                  ) : (
                    <div className={styles.emptySection}>
                      <FileText className={styles.emptySectionIcon} />
                      <p className={styles.emptySectionText}>No summary available for this document</p>
                    </div>
                  )}

                  {/* Navigation */}
                  <div className={styles.documentNavigation}>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const currentIndex = filteredDocuments.findIndex(d => d.id === selectedDocumentId)
                        if (currentIndex > 0) {
                          setSelectedDocumentId(filteredDocuments[currentIndex - 1].id)
                        }
                      }}
                      disabled={filteredDocuments.findIndex(d => d.id === selectedDocumentId) === 0}
                    >
                      ← Previous
                    </Button>
                    <span className={styles.navigationCounter}>
                      {filteredDocuments.findIndex(d => d.id === selectedDocumentId) + 1} of {filteredDocuments.length}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const currentIndex = filteredDocuments.findIndex(d => d.id === selectedDocumentId)
                        if (currentIndex < filteredDocuments.length - 1) {
                          setSelectedDocumentId(filteredDocuments[currentIndex + 1].id)
                        }
                      }}
                      disabled={filteredDocuments.findIndex(d => d.id === selectedDocumentId) === filteredDocuments.length - 1}
                    >
                      Next →
                    </Button>
                  </div>
                </CardContent>
              </>
            ) : (
              <CardContent className={styles.cardContent}>
                <div className={styles.emptySection}>
                  <FileText className={styles.emptySectionIcon} />
                  <p className={styles.emptySectionText}>Select a document to view details</p>
                </div>
              </CardContent>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}