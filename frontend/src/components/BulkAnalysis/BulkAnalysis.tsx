'use client'

import { useState, useEffect } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { Database, RefreshCw, AlertTriangle, CheckCircle, Clock, Zap, AlertCircle, Users, Trash2, Play, Eye, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import styles from './BulkAnalysis.module.scss'

// Types
interface Portal {
  portal_id: string
  agency_name: string
  portal_url: string
  portal_type: string
  credential_status: string
  last_verified: string | null
}

interface CredentialWithPortal {
  portal_id: string
  credential_status: string
  last_verified: string | null
  portals: {
    id: string
    agency_name: string
    portal_url: string
    portal_type: string
  }[]  
}

interface BulkAnalysisJob {
  id: string
  portal_id: string
  job_name: string
  job_description: string | null
  analysis_type: string
  status: string
  priority: number
  progress_data: {
    total_requests: number
    processed_requests: number
    successful_analyses: number
    failed_analyses: number
    skipped_existing: number
    pages_processed: number
    current_page: number
    direction: string
    completion_percentage: number
  }
  resume_info: {
    last_page_processed: number
    can_resume: boolean
    resume_from_page: number
    pagination_test_passed: boolean
    navigation_state: string
  }
  final_results: {
    summary: string
    total_requests_found: number
    new_requests_analyzed: number
    existing_requests_skipped: number
    analysis_errors: number
    pages_covered: number
    processing_time_seconds: number
  }
  error_details: string | null
  retry_count: number
  started_processing_at: string | null
  completed_at: string | null
  estimated_completion_at: string | null
  processing_duration_seconds: number | null
  created_at: string
  updated_at: string
  // Portal information
  agency_name: string
  portal_url: string
  portal_type: string
}

interface JobFormData {
  portal_ids: string[]
  priority: number
}

interface BulkAnalysisProps {
  currentUserId?: string
}

export default function BulkAnalysis({ currentUserId }: BulkAnalysisProps) {
  const supabase = createClientComponentClient()
  
  // State
  const [availablePortals, setAvailablePortals] = useState<Portal[]>([])
  const [analysisJobs, setAnalysisJobs] = useState<BulkAnalysisJob[]>([])
  const [selectedJobs, setSelectedJobs] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  
  // Form state
  const [formData, setFormData] = useState<JobFormData>({
    portal_ids: [],
    priority: 5
  })
  
  // UI state
  const [showJobDetails, setShowJobDetails] = useState<string | null>(null)

  // Load data on component mount
  useEffect(() => {
    loadInitialData()
    
    // Set up real-time subscription for job updates
    const jobsSubscription = supabase
      .channel('bulk_analysis_jobs')
      .on('postgres_changes', 
        { 
          event: '*', 
          schema: 'public', 
          table: 'bulk_analysis_queue',
          filter: `user_id=eq.${currentUserId}`
        }, 
        () => {
          loadAnalysisJobs() // Refresh jobs when changes occur
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(jobsSubscription)
    }
  }, [currentUserId])

  const loadInitialData = async () => {
    if (!currentUserId) {
      setError('User not authenticated')
      setIsLoading(false)
      return
    }

    try {
      setIsLoading(true)
      setError(null)
      
      await Promise.all([
        loadAvailablePortals(),
        loadAnalysisJobs()
      ])

    } catch (err) {
      console.error('Failed to load initial data:', err)
      setError('Failed to load data. Please refresh the page.')
    } finally {
      setIsLoading(false)
    }
  }

  const loadAvailablePortals = async () => {
    try {
      // Use the same RPC as SubmitRequest component
      const { data, error } = await supabase.rpc('get_user_available_portals', { 
        user_uuid: currentUserId 
      })

      if (error) {
        console.error('RPC Error:', error)
        await loadPortalsFallback()
        return
      }

      const verifiedPortals = (data || []).filter((portal: Portal) =>
        portal.credential_status === 'verified'
      )
      
      setAvailablePortals(verifiedPortals)
      
    } catch (err) {
      console.error('Portal loading error:', err)
      await loadPortalsFallback()
    }
  }

  const loadPortalsFallback = async () => {
    try {
      const { data: credentials, error } = await supabase
        .from('user_portal_credentials')
        .select(`
          portal_id,
          credential_status,
          last_verified,
          portals!inner(
            id,
            agency_name,
            portal_url,
            portal_type
          )
        `)
        .eq('user_id', currentUserId)
        .eq('credential_status', 'verified')
      
      if (error) {
        console.error('Credentials query error:', error)
        setAvailablePortals([])
        return
      }
      
      const transformedPortals = (credentials as CredentialWithPortal[] || []).map(cred => ({
        portal_id: cred.portal_id,
        agency_name: cred.portals[0].agency_name, 
        portal_url: cred.portals[0].portal_url,
        portal_type: cred.portals[0].portal_type,
        credential_status: cred.credential_status,
        last_verified: cred.last_verified
      }))
      
      setAvailablePortals(transformedPortals)
      
    } catch (fallbackErr) {
      console.error('Fallback loading error:', fallbackErr)
      setAvailablePortals([])
      setError('Unable to load portal credentials. Please refresh the page.')
    }
  }

  const loadAnalysisJobs = async () => {
    try {
      const { data, error } = await supabase.rpc('get_user_bulk_analysis_jobs', {
        user_uuid: currentUserId
      })

      if (error) throw error

      setAnalysisJobs(data || [])
    } catch (err) {
      console.error('Failed to load analysis jobs:', err)
    }
  }

  const validateForm = (): string | null => {
    if (formData.portal_ids.length === 0) {
      return 'Please select at least one portal'
    }
    
    return null
  }

  const generateJobName = (agencyName: string): string => {
    const date = new Date().toLocaleDateString()
    return `Database Population - ${agencyName} - ${date}`
  }

  const handleSaveDraft = async () => {
    const validationError = validateForm()
    if (validationError) {
      setError(validationError)
      return
    }

    try {
      setIsSubmitting(true)
      setError(null)
      setSuccess(null)

      const jobPromises = formData.portal_ids.map(portalId => {
        const portal = availablePortals.find(p => p.portal_id === portalId)
        const jobData = {
          user_id: currentUserId,
          portal_id: portalId,
          job_name: generateJobName(portal?.agency_name || 'Unknown Agency'),
          job_description: null,
          analysis_type: 'full_analysis', // Always full analysis (incremental handled by backend)
          priority: formData.priority,
          status: 'draft'
        }
        
        return supabase
          .from('bulk_analysis_queue')
          .insert(jobData)
      })

      const results = await Promise.all(jobPromises)
      const errors = results.filter(result => result.error)

      if (errors.length > 0) {
        throw new Error(`Failed to save drafts for ${errors.length} agencies`)
      }

      const selectedAgencies = availablePortals.filter(p => formData.portal_ids.includes(p.portal_id))
      setSuccess(`Analysis jobs saved as drafts for ${selectedAgencies.length} agencies!`)
      
      resetForm()
      await loadAnalysisJobs()

    } catch (err) {
      console.error('Failed to save draft:', err)
      setError('Failed to save draft. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmitNow = async () => {
    const validationError = validateForm()
    if (validationError) {
      setError(validationError)
      return
    }

    try {
      setIsSubmitting(true)
      setError(null)
      setSuccess(null)

      const jobPromises = formData.portal_ids.map(portalId => {
        const portal = availablePortals.find(p => p.portal_id === portalId)
        const jobData = {
          user_id: currentUserId,
          portal_id: portalId,
          job_name: generateJobName(portal?.agency_name || 'Unknown Agency'),
          job_description: null,
          analysis_type: 'full_analysis', // Always full analysis (incremental handled by backend)
          priority: formData.priority,
          status: 'pending'
        }
        
        return supabase
          .from('bulk_analysis_queue')
          .insert(jobData)
      })

      const results = await Promise.all(jobPromises)
      const errors = results.filter(result => result.error)

      if (errors.length > 0) {
        throw new Error(`Failed to submit jobs for ${errors.length} agencies`)
      }

      const selectedAgencies = availablePortals.filter(p => formData.portal_ids.includes(p.portal_id))
      setSuccess(`Analysis jobs submitted for ${selectedAgencies.length} agencies!`)
      
      resetForm()
      await loadAnalysisJobs()

    } catch (err) {
      console.error('Failed to submit jobs:', err)
      setError('Failed to submit jobs. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteJob = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this analysis job?')) return

    try {
      const { error } = await supabase
        .from('bulk_analysis_queue')
        .delete()
        .eq('id', jobId)

      if (error) throw error

      setSuccess('Analysis job deleted successfully!')
      await loadAnalysisJobs()

    } catch (err) {
      console.error('Failed to delete job:', err)
      setError('Failed to delete job. Please try again.')
    }
  }

  const handleSubmitJob = async (jobId: string) => {
    try {
      const { error } = await supabase
        .from('bulk_analysis_queue')
        .update({ 
          status: 'pending',
          updated_at: new Date().toISOString()
        })
        .eq('id', jobId)

      if (error) throw error

      setSuccess('Analysis job submitted successfully!')
      await loadAnalysisJobs()

    } catch (err) {
      console.error('Failed to submit job:', err)
      setError('Failed to submit job. Please try again.')
    }
  }

  const handleBulkSubmit = async () => {
    if (selectedJobs.length === 0) return

    try {
      setIsBulkSubmitting(true)
      setError(null)

      const { error } = await supabase
        .from('bulk_analysis_queue')
        .update({ 
          status: 'pending',
          updated_at: new Date().toISOString()
        })
        .in('id', selectedJobs)

      if (error) throw error

      setSuccess(`${selectedJobs.length} analysis jobs submitted successfully!`)
      setSelectedJobs([])
      await loadAnalysisJobs()

    } catch (err) {
      console.error('Failed to bulk submit:', err)
      setError('Failed to submit selected jobs. Please try again.')
    } finally {
      setIsBulkSubmitting(false)
    }
  }

  const resetForm = () => {
    setFormData({
      portal_ids: [],
      priority: 5
    })
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'draft': return 'statusDraft'
      case 'pending': return 'statusPending'
      case 'processing': return 'statusProcessing'
      case 'completed': return 'statusCompleted'
      case 'failed': return 'statusFailed'
      case 'paused': return 'statusPaused'
      case 'cancelled': return 'statusCancelled'
      default: return 'statusDefault'
    }
  }

  const getPriorityLabel = (priority: number) => {
    if (priority <= 3) return 'High'
    if (priority <= 7) return 'Normal'
    return 'Low'
  }

  const getPriorityColor = (priority: number) => {
    if (priority <= 3) return 'priorityHigh'
    if (priority <= 7) return 'priorityNormal'
    return 'priorityLow'
  }

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return 'N/A'
    
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    } else {
      return `${secs}s`
    }
  }

  const draftJobs = analysisJobs.filter(j => j.status === 'draft')
  const activeJobs = analysisJobs.filter(j => ['pending', 'processing', 'paused'].includes(j.status))
  const completedJobs = analysisJobs.filter(j => ['completed', 'failed', 'cancelled'].includes(j.status))

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <RefreshCw className={styles.loadingIcon} />
          <p className={styles.loadingText}>Loading bulk analysis...</p>
        </div>
      </div>
    )
  }
  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <Database className={styles.icon} />
            </div>
            <div className={styles.headerText}>
              <h1 className={styles.title}>BULK ANALYSIS</h1>
              <p className={styles.subtitle}>
                Populate database with comprehensive request analysis
              </p>
            </div>
          </div>
          
          <div className={styles.headerRight}>
            <div className={styles.headerStats}>
              <div className={styles.stat}>
                <span className={styles.statNumber}>{availablePortals.length}</span>
                <span className={styles.statLabel}>Portals</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statNumber}>{draftJobs.length}</span>
                <span className={styles.statLabel}>Drafts</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statNumber}>{activeJobs.length}</span>
                <span className={styles.statLabel}>Active</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statNumber}>{completedJobs.length}</span>
                <span className={styles.statLabel}>Completed</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error/Success Banners */}
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

      {success && (
        <div className={styles.successBanner}>
          <div className={styles.bannerContent}>
            <CheckCircle className={styles.bannerIcon} />
            <p className={styles.bannerText}>{success}</p>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setSuccess(null)}
              className={styles.bannerDismiss}
            >
              ×
            </Button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className={styles.mainContent}>
        <div className={styles.contentGrid}>
          {/* Left Column - Form */}
          <div className={styles.formColumn}>
            {/* Portal Selection */}
            <Card className={styles.formCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <Users className={styles.titleIcon} />
                  Select Agency Portals
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                {availablePortals.length === 0 ? (
                  <div className={styles.noPortalsWarning}>
                    <AlertCircle className={styles.warningIcon} />
                    <div className={styles.warningContent}>
                      <h4 className={styles.warningTitle}>No Verified Portals Available</h4>
                      <p className={styles.warningText}>
                        You need verified portal credentials to run bulk analysis. 
                        Go to Portal Credentials to set up your accounts.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className={styles.helpText}>
                      Select one or more agency portals to populate your database with comprehensive request analysis. 
                      The system will automatically analyze only new requests not already in your database.
                    </p>
                    
                    <Select 
                      value={formData.portal_ids.length > 0 ? formData.portal_ids[0] : ""} 
                      onValueChange={(value) => {
                        if (!formData.portal_ids.includes(value)) {
                          setFormData(prev => ({ 
                            ...prev, 
                            portal_ids: [...prev.portal_ids, value]
                          }))
                        }
                      }}
                    >
                      <SelectTrigger className={styles.portalSelect}>
                        <SelectValue placeholder={
                          formData.portal_ids.length === 0 
                            ? "Choose agency portals..." 
                            : `${formData.portal_ids.length} agencies selected`
                        } />
                      </SelectTrigger>
                      <SelectContent>
                        {availablePortals.map((portal) => (
                          <SelectItem key={portal.portal_id} value={portal.portal_id}>
                            <div className={styles.portalOption}>
                              <Checkbox
                                checked={formData.portal_ids.includes(portal.portal_id)}
                                onCheckedChange={(checked) => {
                                  if (checked) {
                                    setFormData(prev => ({ 
                                      ...prev, 
                                      portal_ids: [...prev.portal_ids, portal.portal_id]
                                    }))
                                  } else {
                                    setFormData(prev => ({ 
                                      ...prev, 
                                      portal_ids: prev.portal_ids.filter(id => id !== portal.portal_id)
                                    }))
                                  }
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                              <span className={styles.portalName}>{portal.agency_name}</span>
                              <Badge className={styles.portalTypeBadge}>
                                {portal.portal_type.toUpperCase()}
                              </Badge>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {formData.portal_ids.length > 0 && (
                      <div className={styles.selectedAgencies}>
                        {formData.portal_ids.map(portalId => {
                          const portal = availablePortals.find(p => p.portal_id === portalId)
                          return (
                            <Badge key={portalId} className={styles.selectedAgencyBadge}>
                              {portal?.agency_name}
                              <button
                                type="button"
                                onClick={() => setFormData(prev => ({ 
                                  ...prev, 
                                  portal_ids: prev.portal_ids.filter(id => id !== portalId)
                                }))}
                                className={styles.removeBadge}
                              >
                                ×
                              </button>
                            </Badge>
                          )
                        })}
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>

            {/* Priority Selection */}
            <Card className={styles.formCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <Zap className={styles.titleIcon} />
                  Priority Level
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                <p className={styles.helpText}>
                  Set the processing priority. High priority jobs are processed first, 
                  followed by normal and low priority jobs.
                </p>
                
                <Select 
                  value={formData.priority.toString()} 
                  onValueChange={(value) => setFormData(prev => ({ ...prev, priority: parseInt(value) }))}
                >
                  <SelectTrigger className={styles.fieldInput}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">
                      <div className={styles.priorityOption}>
                        <Zap className={styles.priorityIcon} />
                        <span>High Priority - Process immediately</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="5">
                      <div className={styles.priorityOption}>
                        <Clock className={styles.priorityIcon} />
                        <span>Normal Priority - Standard processing</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="9">
                      <div className={styles.priorityOption}>
                        <Clock className={styles.priorityIcon} />
                        <span>Low Priority - Process when available</span>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>

            {/* Submit Buttons */}
            <div className={styles.submitSection}>
              <div className={styles.submitActions}>
                <Button
                  variant="outline"
                  onClick={handleSaveDraft}
                  disabled={isSubmitting || availablePortals.length === 0}
                  className={styles.draftButton}
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className={styles.spinningIcon} />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Clock className={styles.buttonIcon} />
                      Save as Draft
                    </>
                  )}
                </Button>
                <Button
                  onClick={handleSubmitNow}
                  disabled={isSubmitting || availablePortals.length === 0}
                  className={styles.submitButton}
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className={styles.spinningIcon} />
                      Starting...
                    </>
                  ) : (
                    <>
                      <Database className={styles.buttonIcon} />
                      Start Analysis
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>

          {/* Right Column - Job Queue */}
          <div className={styles.sidebarColumn}>
            {/* Draft Jobs */}
            <Card className={styles.queueCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <Clock className={styles.titleIcon} />
                  Draft Jobs
                  {draftJobs.length > 0 && (
                    <Badge className={styles.queueBadge}>
                      {draftJobs.length}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                {draftJobs.length === 0 ? (
                  <div className={styles.emptyQueue}>
                    <p className={styles.emptyText}>No draft jobs</p>
                  </div>
                ) : (
                  <>
                    {/* Bulk Actions */}
                    {selectedJobs.length > 0 && (
                      <div className={styles.bulkActions}>
                        <div className={styles.bulkInfo}>
                          <span className={styles.bulkCount}>
                            {selectedJobs.length} selected
                          </span>
                        </div>
                        <Button
                          size="sm"
                          onClick={handleBulkSubmit}
                          disabled={isBulkSubmitting}
                          className={styles.bulkSubmitButton}
                        >
                          {isBulkSubmitting ? (
                            <>
                              <RefreshCw className={styles.spinningIcon} />
                              Starting...
                            </>
                          ) : (
                            <>
                              <Play className={styles.buttonIcon} />
                              Start All
                            </>
                          )}
                        </Button>
                      </div>
                    )}

                    {/* Draft List */}
                    <div className={styles.queueList}>
                      {draftJobs.map((job) => (
                        <div key={job.id} className={styles.queueItem}>
                          <div className={styles.queueHeader}>
                            <div className={styles.queueCheckbox}>
                              <Checkbox
                                checked={selectedJobs.includes(job.id)}
                                onCheckedChange={(checked) => {
                                  if (checked) {
                                    setSelectedJobs(prev => [...prev, job.id])
                                  } else {
                                    setSelectedJobs(prev => prev.filter(id => id !== job.id))
                                  }
                                }}
                              />
                            </div>
                            <div className={styles.queueTitleSection}>
                              <span className={styles.queueTitle}>
                                {job.agency_name}
                              </span>
                              <Badge className={styles[getStatusColor(job.status)]}>
                                {job.status.toUpperCase()}
                              </Badge>
                            </div>
                          </div>
                          
                          <div className={styles.queueDetails}>
                            <Badge className={styles[getPriorityColor(job.priority)]}>
                              {getPriorityLabel(job.priority)} Priority
                            </Badge>
                          </div>
                          
                          <div className={styles.queueFooter}>
                            <div className={styles.queueDate}>
                              Created {new Date(job.created_at).toLocaleDateString()}
                            </div>
                            
                            <div className={styles.queueActions}>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleSubmitJob(job.id)}
                                className={styles.submitJobButton}
                              >
                                <Play className={styles.actionIcon} />
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleDeleteJob(job.id)}
                                className={styles.deleteJobButton}
                              >
                                <Trash2 className={styles.actionIcon} />
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Active Jobs */}
            {activeJobs.length > 0 && (
              <Card className={styles.queueCard}>
                <CardHeader className={styles.cardHeader}>
                  <CardTitle className={styles.cardTitle}>
                    <RefreshCw className={styles.titleIcon} />
                    Active Jobs
                    <Badge className={styles.queueBadge}>
                      {activeJobs.length}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className={styles.cardContent}>
                  <div className={styles.queueList}>
                    {activeJobs.map((job) => (
                      <div key={job.id} className={styles.queueItem}>
                        <div className={styles.queueHeader}>
                          <div className={styles.queueTitleSection}>
                            <span className={styles.queueTitle}>
                              {job.agency_name}
                            </span>
                            <Badge className={styles[getStatusColor(job.status)]}>
                              {job.status.toUpperCase()}
                            </Badge>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setShowJobDetails(showJobDetails === job.id ? null : job.id)}
                            className={styles.detailsToggle}
                          >
                            <Eye className={styles.actionIcon} />
                          </Button>
                        </div>
                        
                        <div className={styles.queueDetails}>
                          <Badge className={styles[getPriorityColor(job.priority)]}>
                            {getPriorityLabel(job.priority)} Priority
                          </Badge>
                        </div>
                        
                        {/* Progress Bar */}
                        {job.status === 'processing' && (
                          <div className={styles.progressSection}>
                            <div className={styles.progressHeader}>
                              <span className={styles.progressLabel}>
                                {job.progress_data.processed_requests} / {job.progress_data.total_requests || '?'} requests
                              </span>
                              <span className={styles.progressPercentage}>
                                {job.progress_data.completion_percentage}%
                              </span>
                            </div>
                            <Progress 
                              value={job.progress_data.completion_percentage} 
                              className={styles.progressBar}
                            />
                          </div>
                        )}
                        
                        {/* Expanded Details */}
                        {showJobDetails === job.id && (
                          <div className={styles.jobDetails}>
                            <div className={styles.detailsGrid}>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Started:</span>
                                <span className={styles.detailValue}>
                                  {job.started_processing_at 
                                    ? new Date(job.started_processing_at).toLocaleString()
                                    : 'Not started'
                                  }
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Duration:</span>
                                <span className={styles.detailValue}>
                                  {formatDuration(job.processing_duration_seconds)}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Pages Processed:</span>
                                <span className={styles.detailValue}>
                                  {job.progress_data.pages_processed}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Current Page:</span>
                                <span className={styles.detailValue}>
                                  {job.progress_data.current_page || 'N/A'}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Successful:</span>
                                <span className={styles.detailValue}>
                                  {job.progress_data.successful_analyses}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Failed:</span>
                                <span className={styles.detailValue}>
                                  {job.progress_data.failed_analyses}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Skipped:</span>
                                <span className={styles.detailValue}>
                                  {job.progress_data.skipped_existing}
                                </span>
                              </div>
                            </div>
                            
                            {job.error_details && (
                              <div className={styles.errorDetails}>
                                <span className={styles.errorLabel}>Error:</span>
                                <span className={styles.errorText}>{job.error_details}</span>
                              </div>
                            )}
                          </div>
                        )}
                        
                        <div className={styles.queueDate}>
                          Started {new Date(job.created_at).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Completed Jobs */}
            {completedJobs.length > 0 && (
              <Card className={styles.queueCard}>
                <CardHeader className={styles.cardHeader}>
                  <CardTitle className={styles.cardTitle}>
                    <TrendingUp className={styles.titleIcon} />
                    Recent Completions
                    <Badge className={styles.queueBadge}>
                      {completedJobs.length}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className={styles.cardContent}>
                  <div className={styles.queueList}>
                    {completedJobs.slice(0, 5).map((job) => (
                      <div key={job.id} className={styles.queueItem}>
                        <div className={styles.queueHeader}>
                          <div className={styles.queueTitleSection}>
                            <span className={styles.queueTitle}>
                              {job.agency_name}
                            </span>
                            <Badge className={styles[getStatusColor(job.status)]}>
                              {job.status.toUpperCase()}
                            </Badge>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setShowJobDetails(showJobDetails === job.id ? null : job.id)}
                            className={styles.detailsToggle}
                          >
                            <Eye className={styles.actionIcon} />
                          </Button>
                        </div>
                        
                        {/* Results Summary */}
                        {job.status === 'completed' && (
                          <div className={styles.resultsSection}>
                            <div className={styles.resultsSummary}>
                              <div className={styles.resultItem}>
                                <span className={styles.resultNumber}>
                                  {job.final_results.new_requests_analyzed}
                                </span>
                                <span className={styles.resultLabel}>New</span>
                              </div>
                              <div className={styles.resultItem}>
                                <span className={styles.resultNumber}>
                                  {job.final_results.existing_requests_skipped}
                                </span>
                                <span className={styles.resultLabel}>Skipped</span>
                              </div>
                              <div className={styles.resultItem}>
                                <span className={styles.resultNumber}>
                                  {job.final_results.analysis_errors}
                                </span>
                                <span className={styles.resultLabel}>Errors</span>
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* Expanded Results */}
                        {showJobDetails === job.id && (
                          <div className={styles.jobDetails}>
                            <div className={styles.detailsGrid}>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Completed:</span>
                                <span className={styles.detailValue}>
                                  {job.completed_at 
                                    ? new Date(job.completed_at).toLocaleString()
                                    : 'Unknown'
                                  }
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Total Duration:</span>
                                <span className={styles.detailValue}>
                                  {formatDuration(job.processing_duration_seconds)}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Total Requests Found:</span>
                                <span className={styles.detailValue}>
                                  {job.final_results.total_requests_found}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Pages Covered:</span>
                                <span className={styles.detailValue}>
                                  {job.final_results.pages_covered}
                                </span>
                              </div>
                              <div className={styles.detailItem}>
                                <span className={styles.detailLabel}>Retry Count:</span>
                                <span className={styles.detailValue}>
                                  {job.retry_count}
                                </span>
                              </div>
                            </div>
                            
                            {job.final_results.summary && (
                              <div className={styles.summarySection}>
                                <span className={styles.summaryLabel}>Summary:</span>
                                <p className={styles.summaryText}>{job.final_results.summary}</p>
                              </div>
                            )}
                            
                            {job.error_details && (
                              <div className={styles.errorDetails}>
                                <span className={styles.errorLabel}>Error:</span>
                                <span className={styles.errorText}>{job.error_details}</span>
                              </div>
                            )}
                          </div>
                        )}
                        
                        <div className={styles.queueDate}>
                          Completed {new Date(job.completed_at || job.updated_at).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}