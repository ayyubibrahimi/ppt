'use client'

import { useState, useEffect } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { CheckCircle, Clock, AlertTriangle, AlertCircle, RefreshCw, Eye, Search, Filter } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import styles from './SubmissionStatusTab.module.scss'

interface Portal {
  agency_name: string
  portal_url: string
}

interface Request {
  id: string
  request_number: string
  current_status: string
}

interface Submission {
  id: string
  user_id: string
  portal_id: string
  request_topic: string
  request_text: string
  user_notes?: string
  status: string
  queued_for_analysis: boolean
  submitted_request_id: string | null
  submitted_request_number: string | null
  created_at: string
  updated_at: string
  started_processing_at: string | null
  completed_at: string | null
  error_details: string | null
  portals: Portal
  requests: Request | null
}

interface SubmissionStatusTabProps {
  currentUserId?: string
  onViewRequestDetail?: (requestId: string) => void
}

export default function SubmissionStatusTab({
  currentUserId,
  onViewRequestDetail
}: SubmissionStatusTabProps) {
  const supabase = createClientComponentClient()

  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [notesFilter, setNotesFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'analyzed' | 'pending' | 'failed'>('all')
  const [sortBy, setSortBy] = useState<'date' | 'agency' | 'status'>('date')
  const [expandedSubmission, setExpandedSubmission] = useState<string | null>(null)

  useEffect(() => {
    if (currentUserId) {
      loadSubmissions()
    }
  }, [currentUserId])

  const loadSubmissions = async () => {
    if (!currentUserId) return

    try {
      setIsLoading(true)
      setError(null)

      const { data, error: fetchError } = await supabase
        .from('submission_queue')
        .select(`
          *,
          portals!inner(agency_name, portal_url),
          requests(id, request_number, current_status)
        `)
        .eq('user_id', currentUserId)
        .eq('tracked_submission', true)  // Only show tracked submissions (new feature)
        .in('status', ['pending', 'processing', 'completed', 'partial_failure', 'failed'])
        .order('created_at', { ascending: false })

      if (fetchError) throw fetchError

      // Backend now handles linking after bulk analysis completes,
      // so submitted_request_id will be populated for all analyzed requests
      setSubmissions(data || [])
    } catch (err) {
      console.error('Failed to load submissions:', err)
      setError('Failed to load submission status. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const getSubmissionCategory = (submission: Submission): 'analyzed' | 'pending' | 'failed' => {
    if (submission.status === 'failed') {
      return 'failed'
    }

    if (!submission.queued_for_analysis && submission.status === 'completed') {
      return 'failed' // Partial failure
    }

    if (submission.queued_for_analysis && submission.submitted_request_id) {
      return 'analyzed'
    }

    if (submission.queued_for_analysis && !submission.submitted_request_id) {
      return 'pending'
    }

    return 'failed'
  }

  const getStatusInfo = (submission: Submission) => {
    if (submission.status === 'failed') {
      return {
        label: 'Failed',
        color: 'statusFailed',
        icon: AlertCircle,
        description: 'Submission failed completely'
      }
    }

    if (submission.status === 'processing') {
      return {
        label: 'Processing',
        color: 'statusProcessing',
        icon: RefreshCw,
        description: 'Currently being processed'
      }
    }

    if (submission.queued_for_analysis && submission.submitted_request_id) {
      return {
        label: 'Analyzed',
        color: 'statusAnalyzed',
        icon: CheckCircle,
        description: 'Request analyzed and available for monitoring'
      }
    }

    if (submission.queued_for_analysis && !submission.submitted_request_id) {
      return {
        label: 'Pending Analysis',
        color: 'statusPending',
        icon: Clock,
        description: 'Request submitted successfully. Analysis in progress...'
      }
    }

    if (!submission.queued_for_analysis && submission.status === 'completed') {
      return {
        label: 'Partial Failure',
        color: 'statusPartialFailure',
        icon: AlertTriangle,
        description: 'Form submitted but failed to save to database'
      }
    }

    return {
      label: 'Unknown',
      color: 'statusDefault',
      icon: AlertCircle,
      description: 'Unknown status'
    }
  }

  const handleViewDetails = (submission: Submission) => {
    if (submission.submitted_request_id && onViewRequestDetail) {
      onViewRequestDetail(submission.submitted_request_id)
    }
  }

  const handleRetrySubmission = async (submission: Submission) => {
    try {
      const { error } = await supabase
        .from('submission_queue')
        .update({
          status: 'pending',
          error_details: null,
          started_processing_at: null,
          completed_at: null,
          updated_at: new Date().toISOString()
        })
        .eq('id', submission.id)

      if (error) throw error

      // Refresh the submissions list to show the updated status
      await loadSubmissions()
    } catch (err) {
      console.error('Failed to retry submission:', err)
      setError('Failed to retry submission. Please try again.')
    }
  }

  const formatTimestamp = (timestamp: string | null): string => {
    if (!timestamp) return 'N/A'
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    // Relative time for recent submissions
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`

    // Absolute time for older submissions
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
           date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }

  const getRequestPreview = (requestText: string, maxLength: number = 150): string => {
    if (!requestText) return 'No request text available'
    if (requestText.length <= maxLength) return requestText
    return requestText.substring(0, maxLength) + '...'
  }

  const toggleExpanded = (submissionId: string) => {
    setExpandedSubmission(expandedSubmission === submissionId ? null : submissionId)
  }

  // Filter and sort submissions
  const filteredSubmissions = submissions
    .filter(submission => {
      // Search filter
      const matchesSearch = !searchTerm ||
        submission.request_topic?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        submission.request_text?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        submission.portals?.agency_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        submission.submitted_request_number?.toLowerCase().includes(searchTerm.toLowerCase())

      if (!matchesSearch) return false

      // Notes filter
      const matchesNotes = !notesFilter ||
        submission.user_notes?.toLowerCase().includes(notesFilter.toLowerCase())

      if (!matchesNotes) return false

      // Status filter
      if (statusFilter === 'all') return true
      return getSubmissionCategory(submission) === statusFilter
    })
    .sort((a, b) => {
      // Sort logic
      if (sortBy === 'date') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      } else if (sortBy === 'agency') {
        return (a.portals?.agency_name || '').localeCompare(b.portals?.agency_name || '')
      } else if (sortBy === 'status') {
        return a.status.localeCompare(b.status)
      }
      return 0
    })

  // Categorize for stats
  const analyzed = submissions.filter(s => getSubmissionCategory(s) === 'analyzed')
  const pending = submissions.filter(s => getSubmissionCategory(s) === 'pending')
  const failed = submissions.filter(s => getSubmissionCategory(s) === 'failed')

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <RefreshCw className={styles.loadingIcon} />
          <p className={styles.loadingText}>Loading submission status...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      {/* Header with Stats */}
      <div className={styles.header}>
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <CheckCircle className={styles.iconAnalyzed} />
            </div>
            <div className={styles.statContent}>
              <span className={styles.statNumber}>{analyzed.length}</span>
              <span className={styles.statLabel}>Analyzed</span>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <Clock className={styles.iconPending} />
            </div>
            <div className={styles.statContent}>
              <span className={styles.statNumber}>{pending.length}</span>
              <span className={styles.statLabel}>Pending Analysis</span>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <AlertTriangle className={styles.iconFailed} />
            </div>
            <div className={styles.statContent}>
              <span className={styles.statNumber}>{failed.length}</span>
              <span className={styles.statLabel}>Failed</span>
            </div>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className={styles.errorBanner}>
          <div className={styles.bannerContent}>
            <AlertTriangle className={styles.bannerIcon} />
            <p className={styles.bannerText}>{error}</p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setError(null)}
              className={styles.bannerDismiss}
            >
              ×
            </Button>
          </div>
        </div>
      )}

      {/* Filters and Search */}
      <div className={styles.controls}>
        <div className={styles.searchContainer}>
          <Search className={styles.searchIcon} />
          <Input
            placeholder="Search submissions..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className={styles.searchInput}
          />
        </div>

        <div className={styles.searchContainer}>
          <Filter className={styles.searchIcon} />
          <Input
            placeholder="Filter by notes..."
            value={notesFilter}
            onChange={(e) => setNotesFilter(e.target.value)}
            className={styles.searchInput}
          />
        </div>

        <div className={styles.filterButtons}>
          <Button
            variant={statusFilter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('all')}
            className={styles.filterButton}
          >
            All ({submissions.length})
          </Button>
          <Button
            variant={statusFilter === 'analyzed' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('analyzed')}
            className={styles.filterButton}
          >
            Analyzed ({analyzed.length})
          </Button>
          <Button
            variant={statusFilter === 'pending' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('pending')}
            className={styles.filterButton}
          >
            Pending ({pending.length})
          </Button>
          <Button
            variant={statusFilter === 'failed' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('failed')}
            className={styles.filterButton}
          >
            Failed ({failed.length})
          </Button>
        </div>

        <div className={styles.sortContainer}>
          <Filter className={styles.sortIcon} />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'date' | 'agency' | 'status')}
            className={styles.sortSelect}
          >
            <option value="date">Sort by Date</option>
            <option value="agency">Sort by Agency</option>
            <option value="status">Sort by Status</option>
          </select>
        </div>

        <Button
          onClick={loadSubmissions}
          disabled={isLoading}
          className={styles.refreshButton}
        >
          <RefreshCw className={`${styles.refreshIcon} ${isLoading ? styles.spinning : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Submissions List */}
      <div className={styles.content}>
        {filteredSubmissions.length === 0 ? (
          <div className={styles.emptyState}>
            <AlertCircle className={styles.emptyIcon} />
            <h3 className={styles.emptyTitle}>No submissions found</h3>
            <p className={styles.emptyText}>
              {searchTerm || statusFilter !== 'all'
                ? 'Try adjusting your filters or search term'
                : 'Submit your first request to see it here'}
            </p>
          </div>
        ) : (
          <div className={styles.submissionsList}>
            {filteredSubmissions.map((submission) => {
              const statusInfo = getStatusInfo(submission)
              const StatusIcon = statusInfo.icon
              const category = getSubmissionCategory(submission)

              return (
                <Card key={submission.id} className={`${styles.submissionCard} ${styles[category]}`}>
                  <CardContent className={styles.cardContent}>
                    {/* Header: Topic + Status + Request Number */}
                    <div className={styles.submissionHeader}>
                      <div className={styles.submissionTitle}>
                        <h4 className={styles.requestTopic}>
                          {submission.request_topic || 'Untitled Request'}
                        </h4>
                        {submission.submitted_request_number && (
                          <span className={styles.requestNumber}>
                            #{submission.submitted_request_number}
                          </span>
                        )}
                      </div>
                      <Badge className={styles[statusInfo.color]}>
                        <StatusIcon className={styles.badgeIcon} />
                        {statusInfo.label}
                      </Badge>
                    </div>

                    {/* Meta: Agency + Portal URL */}
                    <div className={styles.submissionMeta}>
                      <span className={styles.metaAgency}>
                        {submission.portals?.agency_name}
                      </span>
                      {submission.portals?.portal_url && (
                        <span className={styles.metaPortalUrl}>
                          • {submission.portals.portal_url}
                        </span>
                      )}
                    </div>

                    {/* Timestamps */}
                    <div className={styles.timestamps}>
                      <span className={styles.timestamp}>
                        <strong>Created:</strong> {formatTimestamp(submission.created_at)}
                      </span>
                      {submission.started_processing_at && (
                        <span className={styles.timestamp}>
                          <strong>Started:</strong> {formatTimestamp(submission.started_processing_at)}
                        </span>
                      )}
                      {submission.completed_at && (
                        <span className={styles.timestamp}>
                          <strong>Completed:</strong> {formatTimestamp(submission.completed_at)}
                        </span>
                      )}
                    </div>

                    {/* Request Text Preview */}
                    <div className={styles.requestPreview}>
                      <p className={styles.previewText}>
                        {getRequestPreview(submission.request_text)}
                      </p>
                      {submission.request_text && submission.request_text.length > 150 && (
                        <button
                          onClick={() => toggleExpanded(submission.id)}
                          className={styles.expandButton}
                        >
                          {expandedSubmission === submission.id ? 'Show Less' : 'Show More'}
                        </button>
                      )}
                    </div>

                    {/* User Notes */}
                    {submission.user_notes && (
                      <div className={styles.submissionNotes}>
                        <Filter className={styles.notesIcon} />
                        <span className={styles.notesText}>{submission.user_notes}</span>
                      </div>
                    )}

                    {/* Expanded Details */}
                    {expandedSubmission === submission.id && (
                      <div className={styles.expandedDetails}>
                        <div className={styles.fullRequestText}>
                          <strong>Full Request:</strong>
                          <p>{submission.request_text}</p>
                        </div>
                        {submission.error_details && (
                          <div className={styles.errorDetailsExpanded}>
                            <strong>Error Details:</strong>
                            <p>{submission.error_details}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Progress bar for pending items */}
                    {category === 'pending' && (
                      <div className={styles.progressBar}>
                        <div className={styles.progressFill} style={{ width: '60%' }} />
                      </div>
                    )}

                    {/* Error message for failed items */}
                    {submission.error_details && (
                      <div className={styles.errorMessage}>
                        <AlertCircle className={styles.errorIcon} />
                        {submission.error_details}
                      </div>
                    )}

                    {/* Actions - View Details button for analyzed, Retry for failed */}
                    <div className={styles.submissionActions}>
                      {submission.submitted_request_id && onViewRequestDetail && (
                        <Button
                          onClick={() => handleViewDetails(submission)}
                          className={styles.viewDetailsButton}
                        >
                          <Eye className={styles.buttonIcon} />
                          View Request Details
                        </Button>
                      )}
                      {category === 'failed' && (
                        <Button
                          onClick={() => handleRetrySubmission(submission)}
                          className={styles.retryButton}
                        >
                          <RefreshCw className={styles.buttonIcon} />
                          Retry Submission
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
