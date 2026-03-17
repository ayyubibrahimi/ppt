'use client'

import { useState, useEffect } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { Send, FileText, User, AlertTriangle, CheckCircle, Clock, RefreshCw, Zap, AlertCircle, Eye, Users, Edit3, Trash2, Save, Play, List } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import SubmissionStatusTab from './SubmissionStatusTab'
import styles from './SubmitRequest.module.scss'

// Types
interface Portal {
  portal_id: string
  agency_name: string
  portal_url: string
  portal_type: string
  credential_status: string
  last_verified: string | null
}

interface UserInfo {
  id: string
  email: string
  full_name: string
  phone?: string
  organization?: string
}

interface QueuedSubmission {
  id: string
  portal_id: string
  request_topic: string
  request_text: string
  user_notes?: string
  status: string
  priority: number
  created_at: string
  updated_at: string
  requester_info: {
    first_name: string
    last_name: string
    email: string
    phone: string
    organization: string
    address: string
    city: string
    state: string
    zip: string
  }
  agency_name?: string
  portal_type?: string
}

interface RequestFormData {
  portal_ids: string[]
  request_topic: string
  request_text: string
  user_notes: string
  priority: number
  requester_info: {
    first_name: string
    last_name: string
    email: string
    phone: string
    organization: string
    address: string
    city: string
    state: string
    zip: string
  }
}
interface CredentialWithPortal {
  portal_id: string
  credential_status: string
  last_verified: string | null
  portals: {
    portal_id: string
    agency_name: string
    portal_url: string
    portal_type: string
  }[]
}

// Hardcoded test user ID - replace with your actual test user ID
const TEST_USER_ID = '3faca167-f566-44a8-bdcc-343d5a00c2ac'

// Request templates
const REQUEST_TEMPLATES = [
  {
    title: "Police Reports",
    content: "I am requesting copies of all police reports related to incident number [INCIDENT_NUMBER] that occurred on [DATE] at [LOCATION]. Please include all supplemental reports, witness statements, and any related documentation."
  },
  {
    title: "Meeting Minutes",
    content: "I am requesting copies of all meeting minutes, agendas, and related materials from [DEPARTMENT/BOARD] meetings held between [START_DATE] and [END_DATE]. Please include any audio or video recordings if available."
  },
  {
    title: "Contracts & Agreements",
    content: "I am requesting copies of all contracts, agreements, and related documentation between [AGENCY_NAME] and [CONTRACTOR/VENDOR] for the period of [DATE_RANGE]. Please include any amendments, change orders, and payment records."
  },
  {
    title: "Personnel Records",
    content: "I am requesting the personnel file for [EMPLOYEE_NAME], badge/ID number [BADGE_NUMBER], including disciplinary records, training records, and any complaints filed. Please redact personal information as required by law."
  }
]

interface SubmitRequestProps {
    currentUserId?: string
    onViewRequestDetail?: (requestId: string) => void
  }

  export default function SubmitRequest({ currentUserId, onViewRequestDetail }: SubmitRequestProps) {
  const supabase = createClientComponentClient()

  // State
  const [activeTab, setActiveTab] = useState<'compose' | 'status'>('compose')
  const [availablePortals, setAvailablePortals] = useState<Portal[]>([])
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null)
  const [queuedSubmissions, setQueuedSubmissions] = useState<QueuedSubmission[]>([])
  const [selectedDrafts, setSelectedDrafts] = useState<string[]>([])
  const [editingDraft, setEditingDraft] = useState<QueuedSubmission | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  
  // Form state
  const [formData, setFormData] = useState<RequestFormData>({
    portal_ids: [],
    request_topic: '',
    request_text: '',
    user_notes: '',
    priority: 5,
    requester_info: {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      organization: '',
      address: '',
      city: '',
      state: '',
      zip: ''
    }
  })
  
  // UI state
  const [showTemplates, setShowTemplates] = useState(false)
  const [characterCount, setCharacterCount] = useState(0)
  const [portalTypeFilter, setPortalTypeFilter] = useState<'all' | 'email' | 'nextrequest' | 'govqa' | 'portal'>('all')

  // Load data on component mount
  useEffect(() => {
    loadInitialData()
  }, [])

  // Update character count when request text changes
  useEffect(() => {
    setCharacterCount(formData.request_text.length)
  }, [formData.request_text])

  // Infer department type from agency name (same logic as PortalCredentials)
  const inferDepartmentType = (agencyName: string): 'police' | 'sheriff' | 'district_attorney' | 'other' => {
    const name = agencyName.toLowerCase()
    if (name.includes('police') || name.includes('pd')) {
      return 'police'
    } else if (name.includes('sheriff')) {
      return 'sheriff'
    } else if (name.includes('district attorney') || name.includes('da ') || name.includes("da's")) {
      return 'district_attorney'
    }
    return 'other'
  }

  // Handle bulk selection by department type or portal type
  const handleBulkSelection = (action: 'all' | 'police' | 'sheriff' | 'district_attorney' | 'other' | 'email' | 'nextrequest' | 'govqa' | 'portal' | 'clear') => {
    if (action === 'clear') {
      setFormData(prev => ({ ...prev, portal_ids: [] }))
      return
    }

    if (action === 'all') {
      setFormData(prev => ({
        ...prev,
        portal_ids: availablePortals.map(p => p.portal_id)
      }))
      return
    }

    // Filter by portal type
    if (action === 'email' || action === 'nextrequest' || action === 'govqa' || action === 'portal') {
      const filteredPortals = availablePortals.filter(portal =>
        portal.portal_type === action
      )
      setFormData(prev => ({
        ...prev,
        portal_ids: filteredPortals.map(p => p.portal_id)
      }))
      return
    }

    // Filter by department type
    const filteredPortals = availablePortals.filter(portal =>
      inferDepartmentType(portal.agency_name) === action
    )
    setFormData(prev => ({
      ...prev,
      portal_ids: filteredPortals.map(p => p.portal_id)
    }))
  }

  // Get counts for each department type
  const departmentCounts = {
    all: availablePortals.length,
    police: availablePortals.filter(p => inferDepartmentType(p.agency_name) === 'police').length,
    sheriff: availablePortals.filter(p => inferDepartmentType(p.agency_name) === 'sheriff').length,
    district_attorney: availablePortals.filter(p => inferDepartmentType(p.agency_name) === 'district_attorney').length,
    other: availablePortals.filter(p => inferDepartmentType(p.agency_name) === 'other').length,
  }

  // Get counts for each portal type
  const portalTypeCounts = {
    all: availablePortals.length,
    email: availablePortals.filter(p => p.portal_type === 'email').length,
    nextrequest: availablePortals.filter(p => p.portal_type === 'nextrequest').length,
    govqa: availablePortals.filter(p => p.portal_type === 'govqa').length,
    portal: availablePortals.filter(p => p.portal_type === 'portal').length,
  }

  const loadInitialData = async () => {
    console.log('=== LOADING INITIAL DATA ===')
    console.log('Current user ID:', currentUserId)
    
    if (!currentUserId) {
      console.log('No currentUserId provided')
      setError('User not authenticated')
      setIsLoading(false)
      return
    }  
  
    try {
      setIsLoading(true)
      setError(null)
      
      console.log('Starting parallel data loading...')
  
      // Load data with individual error handling and timeouts
      const loadPromises = [
        loadAvailablePortals().catch(err => {
          console.error('Portal loading failed:', err)
          return null // Don't fail the whole process
        }),
        loadUserInfo().catch(err => {
          console.error('User info loading failed:', err)
          return null
        }),
        loadQueuedSubmissions().catch(err => {
          console.error('Queue loading failed:', err)
          return null
        })
      ]
  
      // Set a global timeout for all operations
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Data loading timeout after 15 seconds')), 15000)
      )
  
      const results = await Promise.race([
        Promise.allSettled(loadPromises),
        timeoutPromise
      ])
  
      console.log('All data loading operations completed')
      console.log('Results:', results)
  
    } catch (err) {
      console.error('=== INITIAL DATA LOADING ERROR ===')
      console.error('Error details:', err)
      
      // Set a user-friendly error message
      if (err instanceof Error && err.message.includes('timeout')) {
        setError('Loading is taking longer than expected. Please refresh the page.')
      } else {
        setError('Failed to load form data. Please refresh the page.')
      }
    } finally {
      setIsLoading(false)
      console.log('=== INITIAL DATA LOADING COMPLETE ===')
    }
  }

  const loadAvailablePortals = async () => {
    try {
      console.log('=== LOADING AVAILABLE PORTALS ===')
      console.log('Current user ID:', currentUserId)
      console.log('User authenticated:', !!currentUserId)
      
      if (!currentUserId) {
        console.log('No currentUserId provided, skipping portal load')
        setAvailablePortals([])
        return
      }
  
      console.log('Calling get_user_available_portals RPC...')
      
      // Create the RPC promise
      const rpcPromise = supabase.rpc('get_user_available_portals', { 
        user_uuid: currentUserId 
      })
      
      // Add a timeout wrapper
      const timeoutPromise = new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error('RPC call timeout after 10 seconds')), 10000)
      )
      
      const { data, error } = await Promise.race([rpcPromise, timeoutPromise])
      
      console.log('RPC response received')
      console.log('RPC data:', data)
      console.log('RPC error:', error)
  
      if (error) {
        console.error('RPC Error details:', {
          message: error.message,
          details: error.details,
          hint: error.hint,
          code: error.code
        })
        
        // If RPC doesn't exist or fails, fall back to direct query
        console.log('Falling back to direct portal credentials query...')
        return await loadPortalsFallback()
      }
  
      // Filter to only verified credentials
      const verifiedPortals = (data || []).filter((portal: Portal) => {
        console.log('Portal credential status:', portal.credential_status)
        return portal.credential_status === 'verified'
      })
  
      console.log('Verified portals found:', verifiedPortals.length)
      console.log('Verified portals:', verifiedPortals)
      
      setAvailablePortals(verifiedPortals)
      console.log('=== PORTAL LOADING COMPLETE ===')
      
    } catch (err) {
      console.error('=== PORTAL LOADING ERROR ===')
      console.error('Error type:', typeof err)
      console.error('Error message:', err instanceof Error ? err.message : 'Unknown error')
      console.error('Error stack:', err instanceof Error ? err.stack : 'No stack trace')
      console.error('Full error object:', err)
      
      // Try fallback method
      console.log('Attempting fallback method...')
      await loadPortalsFallback()
    }
  }
  
  // Fallback method using direct table queries
  const loadPortalsFallback = async () => {
    try {
      console.log('=== FALLBACK PORTAL LOADING ===')
      
      // Direct query to portal_credentials table
      const { data: credentials, error: credError } = await supabase
        .from('portal_credentials')
        .select(`
          portal_id,
          credential_status,
          last_verified,
          portals!inner(
            portal_id,
            agency_name,
            portal_url,
            portal_type
          )
        `)
        .eq('user_id', currentUserId)
        .eq('credential_status', 'verified')
      
      console.log('Direct credentials query result:', { credentials, credError })
      
      if (credError) {
        console.error('Credentials query error:', credError)
        // If even the fallback fails, just set empty array
        setAvailablePortals([])
        return
      }
      
      // Transform data to match expected format
      const transformedPortals = (credentials as CredentialWithPortal[] || []).map(cred => ({
        portal_id: cred.portal_id,
        agency_name: cred.portals[0].agency_name,
        portal_url: cred.portals[0].portal_url,
        portal_type: cred.portals[0].portal_type,
        credential_status: cred.credential_status,
        last_verified: cred.last_verified
      }))
      
      console.log('Transformed portals:', transformedPortals)
      setAvailablePortals(transformedPortals)
      console.log('=== FALLBACK LOADING COMPLETE ===')
      
    } catch (fallbackErr) {
      console.error('=== FALLBACK LOADING ERROR ===')
      console.error('Fallback error:', fallbackErr)
      
      // Last resort - set empty array so UI doesn't hang
      setAvailablePortals([])
      setError('Unable to load portal credentials. Please refresh the page or contact support.')
    }
  }

  const loadUserInfo = async () => {
    try {
        const { data, error } = await supabase
        .from('users')
        .select('*')
        .eq('id', currentUserId)
        .single()

      if (error) throw error

      if (data) {
        setUserInfo(data)
        
        // Parse full name
        const nameParts = (data.full_name || '').split(' ')
        const firstName = nameParts[0] || ''
        const lastName = nameParts.slice(1).join(' ') || ''
        
        // Pre-fill form with user data
        setFormData(prev => ({
          ...prev,
          requester_info: {
            ...prev.requester_info,
            first_name: firstName,
            last_name: lastName,
            email: data.email || '',
            phone: data.phone || '',
            organization: data.organization || ''
          }
        }))
      }
    } catch (err) {
      console.error('Failed to load user info:', err)
    }
  }

  const loadQueuedSubmissions = async () => {
    try {
      // Load submissions with portal info
      const { data, error } = await supabase
        .from('submission_queue')
        .select(`
          *,
          portals!inner(agency_name, portal_type)
        `)
        .eq('user_id', currentUserId)
        .in('status', ['draft', 'pending'])
        .order('created_at', { ascending: false })

      if (error) throw error

      // Transform data to include agency info
      const transformedData = (data || []).map(submission => ({
        ...submission,
        agency_name: submission.portals?.agency_name,
        portal_type: submission.portals?.portal_type
      }))

      setQueuedSubmissions(transformedData)
    } catch (err) {
      console.error('Failed to load queued submissions:', err)
    }
  }

  const handleTemplateSelect = (template: string) => {
    setFormData(prev => ({
      ...prev,
      request_text: template
    }))
    setShowTemplates(false)
  }

  const validateForm = (): string | null => {
    if (formData.portal_ids.length === 0) {
        return 'Please select at least one portal'
      }
    
    if (!formData.request_text.trim()) {
      return 'Please enter your request text'
    }
    
    if (formData.request_text.length < 50) {
      return 'Request text should be at least 50 characters'
    }
    
    if (!formData.requester_info.first_name.trim() || !formData.requester_info.last_name.trim()) {
      return 'Please enter your full name'
    }
    
    if (!formData.requester_info.email.trim()) {
      return 'Please enter your email address'
    }
    
    return null
  }

  // NEW - Replace handleSaveDraft function:
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
  
      const submissionPromises = formData.portal_ids.map(portalId => {
        const submissionData = {
          user_id: currentUserId,
          portal_id: portalId,
          request_text: formData.request_text,
          request_topic: formData.request_topic || 'Public Records Request',
          user_notes: formData.user_notes || null,
          requester_info: formData.requester_info,
          priority: formData.priority,
          status: 'draft',
          tracked_submission: true  // Enable tracking for new submissions
        }

        return supabase
          .from('submission_queue')
          .insert(submissionData)
      })
  
      const results = await Promise.all(submissionPromises)
      const errors = results.filter(result => result.error)
  
      if (errors.length > 0) {
        throw new Error(`Failed to save drafts to ${errors.length} agencies`)
      }
  
      const selectedAgencies = availablePortals.filter(p => formData.portal_ids.includes(p.portal_id))
      setSuccess(`Drafts saved successfully for ${selectedAgencies.length} agencies!`)
      
      resetForm()
      await loadQueuedSubmissions()
  
    } catch (err) {
      console.error('Failed to save draft:', err)
      setError('Failed to save draft. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // NEW - Replace handleSubmitNow function:
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
  
      const submissionPromises = formData.portal_ids.map(portalId => {
        const submissionData = {
          user_id: currentUserId,
          portal_id: portalId,
          request_text: formData.request_text,
          request_topic: formData.request_topic || 'Public Records Request',
          user_notes: formData.user_notes || null,
          requester_info: formData.requester_info,
          priority: formData.priority,
          status: 'pending',
          tracked_submission: true  // Enable tracking for new submissions
        }

        return supabase
          .from('submission_queue')
          .insert(submissionData)
      })
  
      const results = await Promise.all(submissionPromises)
      const errors = results.filter(result => result.error)
  
      if (errors.length > 0) {
        throw new Error(`Failed to submit to ${errors.length} agencies`)
      }
  
      const selectedAgencies = availablePortals.filter(p => formData.portal_ids.includes(p.portal_id))
      setSuccess(`Requests submitted successfully to ${selectedAgencies.length} agencies!`)
      
      resetForm()
      await loadQueuedSubmissions()
  
    } catch (err) {
      console.error('Failed to submit request:', err)
      setError('Failed to submit request. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEditDraft = (draft: QueuedSubmission) => {
    setEditingDraft(draft)

    // Load draft data into form
    setFormData({
    portal_ids: [draft.portal_id],
      request_topic: draft.request_topic,
      request_text: draft.request_text,
      user_notes: draft.user_notes || '',
      priority: draft.priority,
      requester_info: draft.requester_info || formData.requester_info
    })
  }

  const handleUpdateDraft = async () => {
    if (!editingDraft) return
    
    const validationError = validateForm()
    if (validationError) {
      setError(validationError)
      return
    }

    try {
      setIsSubmitting(true)
      setError(null)

      const updateData = {
        portal_id: formData.portal_ids[0],
        request_text: formData.request_text,
        request_topic: formData.request_topic,
        user_notes: formData.user_notes || null,
        requester_info: formData.requester_info,
        priority: formData.priority,
        updated_at: new Date().toISOString()
      }

      const { error } = await supabase
        .from('submission_queue')
        .update(updateData)
        .eq('id', editingDraft.id)

      if (error) throw error

      setSuccess('Draft updated successfully!')
      setEditingDraft(null)
      resetForm()
      await loadQueuedSubmissions()

    } catch (err) {
      console.error('Failed to update draft:', err)
      setError('Failed to update draft. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteDraft = async (draftId: string) => {
    if (!confirm('Are you sure you want to delete this draft?')) return

    try {
      const { error } = await supabase
        .from('submission_queue')
        .delete()
        .eq('id', draftId)

      if (error) throw error

      setSuccess('Draft deleted successfully!')
      await loadQueuedSubmissions()
      
      // Clear editing state if we're editing this draft
      if (editingDraft?.id === draftId) {
        setEditingDraft(null)
        resetForm()
      }

    } catch (err) {
      console.error('Failed to delete draft:', err)
      setError('Failed to delete draft. Please try again.')
    }
  }

  const handleSubmitDraft = async (draftId: string) => {
    try {
      const { error } = await supabase
        .from('submission_queue')
        .update({ 
          status: 'pending',
          updated_at: new Date().toISOString()
        })
        .eq('id', draftId)

      if (error) throw error

      setSuccess('Draft submitted successfully!')
      await loadQueuedSubmissions()

    } catch (err) {
      console.error('Failed to submit draft:', err)
      setError('Failed to submit draft. Please try again.')
    }
  }

  const handleBulkSubmit = async () => {
    if (selectedDrafts.length === 0) return

    try {
      setIsBulkSubmitting(true)
      setError(null)

      const { error } = await supabase
        .from('submission_queue')
        .update({ 
          status: 'pending',
          updated_at: new Date().toISOString()
        })
        .in('id', selectedDrafts)

      if (error) throw error

      setSuccess(`${selectedDrafts.length} drafts submitted successfully!`)
      setSelectedDrafts([])
      await loadQueuedSubmissions()

    } catch (err) {
      console.error('Failed to bulk submit:', err)
      setError('Failed to submit selected drafts. Please try again.')
    } finally {
      setIsBulkSubmitting(false)
    }
  }

  const resetForm = () => {
    setFormData(prev => ({
      ...prev,
      portal_ids: [],
      request_topic: '',
      request_text: '',
      user_notes: '',
      priority: 5
    }))
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'draft': return 'statusDraft'
      case 'pending': return 'statusPending'
      case 'processing': return 'statusProcessing'
      case 'completed': return 'statusCompleted'
      case 'failed': return 'statusFailed'
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

  const draftSubmissions = queuedSubmissions.filter(s => s.status === 'draft')
  const pendingSubmissions = queuedSubmissions.filter(s => s.status === 'pending')

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <RefreshCw className={styles.loadingIcon} />
          <p className={styles.loadingText}>Loading submission form...</p>
        </div>
      </div>
    )
  }

  const handleSmartPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>, currentValue: string, onChange: (value: string) => void) => {
    e.preventDefault()
    
    const clipboardData = e.clipboardData
    const htmlData = clipboardData.getData('text/html')
    const textData = clipboardData.getData('text/plain')
    
    let processedText = textData
    
    // If we have HTML data, try to preserve basic formatting
    if (htmlData) {
      // Create a temporary div to parse HTML
      const tempDiv = document.createElement('div')
      tempDiv.innerHTML = htmlData
      
      // Convert common HTML elements to text equivalents
      // Preserve bullet points
      tempDiv.querySelectorAll('li').forEach(li => {
        const text = li.textContent || li.innerText
        li.innerHTML = `• ${text}`
      })
      
      // Convert <ul> and <ol> to text with proper spacing
      tempDiv.querySelectorAll('ul, ol').forEach(list => {
        const items = Array.from(list.querySelectorAll('li'))
        const listText = items.map(item => item.textContent || item.innerText).join('\n')
        list.innerHTML = listText
      })
      
      // Convert <p> to line breaks
      tempDiv.querySelectorAll('p').forEach(p => {
        p.innerHTML = p.innerHTML + '\n'
      })
      
      // Convert <br> to line breaks
      tempDiv.querySelectorAll('br').forEach(br => {
        br.innerHTML = '\n'
      })
      
      processedText = tempDiv.textContent || tempDiv.innerText || textData
    }
    
    // Clean up extra whitespace but preserve intentional formatting
    processedText = processedText
      .replace(/\n\s*\n\s*\n/g, '\n\n') // Max 2 consecutive line breaks
      .trim()
    
    // Get cursor position
    const textarea = e.target as HTMLTextAreaElement
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    
    // Insert processed text at cursor position
    const newValue = currentValue.substring(0, start) + processedText + currentValue.substring(end)
    
    // Update the form data
    onChange(newValue)
    
    // Set cursor position after pasted content
    setTimeout(() => {
      textarea.selectionStart = textarea.selectionEnd = start + processedText.length
      textarea.focus()
    }, 0)
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <Send className={styles.icon} />
            </div>
            <div className={styles.headerText}>
              <h1 className={styles.title}>SUBMIT REQUEST</h1>
              <p className={styles.subtitle}>
                Create and manage public records requests
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
                <span className={styles.statNumber}>{draftSubmissions.length}</span>
                <span className={styles.statLabel}>Drafts</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statNumber}>{pendingSubmissions.length}</span>
                <span className={styles.statLabel}>Pending</span>
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

      {/* Tab Navigation */}
      <div className={styles.tabNavigation}>
        <div className={styles.tabContainer}>
          <button
            onClick={() => setActiveTab('compose')}
            className={`${styles.tab} ${activeTab === 'compose' ? styles.tabActive : ''}`}
          >
            <Send className={styles.tabIcon} />
            <span className={styles.tabLabel}>COMPOSE REQUEST</span>
          </button>

          <button
            onClick={() => setActiveTab('status')}
            className={`${styles.tab} ${activeTab === 'status' ? styles.tabActive : ''}`}
          >
            <List className={styles.tabIcon} />
            <span className={styles.tabLabel}>SUBMISSION STATUS</span>
          </button>
        </div>
      </div>

      {/* Main Content */}
      {activeTab === 'compose' ? (
      <div className={styles.mainContent}>
        <div className={styles.contentGrid}>
          {/* Left Column - Form */}
          <div className={styles.formColumn}>
            {/* Portal Selection */}
            <Card className={styles.formCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <Users className={styles.titleIcon} />
                  {editingDraft ? 'Edit Draft Request' : 'Select Agency Portal'}
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                {availablePortals.length === 0 ? (
                  <div className={styles.noPortalsWarning}>
                    <AlertCircle className={styles.warningIcon} />
                    <div className={styles.warningContent}>
                      <h4 className={styles.warningTitle}>No Verified Portals Available</h4>
                      <p className={styles.warningText}>
                        You need to add and verify portal credentials before submitting requests. 
                        Go to Portal Credentials to set up your accounts.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Bulk Selection Dropdown */}
                    <div className={styles.bulkSelectionContainer}>
                      <label className={styles.bulkSelectionLabel}>Bulk Select:</label>
                      <Select onValueChange={(value) => handleBulkSelection(value as any)}>
                        <SelectTrigger className={styles.bulkSelectTrigger}>
                          <SelectValue placeholder="Select agencies..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">
                            All Agencies ({departmentCounts.all})
                          </SelectItem>

                          {/* Portal Type Filters */}
                          {portalTypeCounts.email > 0 && (
                            <SelectItem value="email">
                              All Email-Based Agencies ({portalTypeCounts.email})
                            </SelectItem>
                          )}
                          {portalTypeCounts.nextrequest > 0 && (
                            <SelectItem value="nextrequest">
                              All NextRequest Portals ({portalTypeCounts.nextrequest})
                            </SelectItem>
                          )}
                          {portalTypeCounts.govqa > 0 && (
                            <SelectItem value="govqa">
                              All GovQA Portals ({portalTypeCounts.govqa})
                            </SelectItem>
                          )}
                          {portalTypeCounts.portal > 0 && (
                            <SelectItem value="portal">
                              All Other Portals ({portalTypeCounts.portal})
                            </SelectItem>
                          )}

                          {/* Department Type Filters */}
                          {departmentCounts.police > 0 && (
                            <SelectItem value="police">
                              All Police Departments ({departmentCounts.police})
                            </SelectItem>
                          )}
                          {departmentCounts.sheriff > 0 && (
                            <SelectItem value="sheriff">
                              All Sheriff Departments ({departmentCounts.sheriff})
                            </SelectItem>
                          )}
                          {departmentCounts.district_attorney > 0 && (
                            <SelectItem value="district_attorney">
                              All District Attorney Offices ({departmentCounts.district_attorney})
                            </SelectItem>
                          )}
                          {departmentCounts.other > 0 && (
                            <SelectItem value="other">
                              All Other Agencies ({departmentCounts.other})
                            </SelectItem>
                          )}
                          <SelectItem value="clear">
                            Clear All Selections
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

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
  
                    {/* Move selected agencies OUTSIDE of Select component */}
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
  
            {/* Request Details */}
            <Card className={styles.formCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <FileText className={styles.titleIcon} />
                  Request Details
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>                
                <div className={styles.formField}>
                  <div className={styles.fieldHeader}>
                    <label className={styles.fieldLabel}>Request Text *</label>
                    <div className={styles.fieldTools}>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setShowTemplates(!showTemplates)}
                        className={styles.templateButton}
                      >
                        <Eye className={styles.buttonIcon} />
                        Templates
                      </Button>
                      <span className={styles.characterCount}>
                        {characterCount.toLocaleString()} characters
                      </span>
                    </div>
                  </div>
                  
                  {showTemplates && (
                    <div className={styles.templatesSection}>
                      <h4 className={styles.templatesTitle}>Request Templates</h4>
                      <div className={styles.templatesList}>
                        {REQUEST_TEMPLATES.map((template, index) => (
                          <button
                            key={index}
                            type="button"
                            onClick={() => handleTemplateSelect(template.content)}
                            className={styles.templateItem}
                          >
                            <span className={styles.templateTitle}>{template.title}</span>
                            <span className={styles.templatePreview}>
                              {template.content.substring(0, 100)}...
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  <Textarea
                    value={formData.request_text}
                    onChange={(e) => setFormData(prev => ({ ...prev, request_text: e.target.value }))}
                    onPaste={(e) => handleSmartPaste(e, formData.request_text, (newText) => 
                        setFormData(prev => ({ ...prev, request_text: newText }))
                    )}
                    placeholder="Enter your detailed public records request. Be specific about what documents, time periods, and information you are seeking... (Paste formatted text to preserve bullet points)"
                    className={styles.requestTextarea}
                    rows={12}
                    />
                  
                  <div className={styles.fieldHint}>
                    <div className={styles.hintText}>
                      Be specific and detailed. Include dates, locations, document types, and any other relevant information.
                    </div>
                  </div>
                </div>

                <div className={styles.formField}>
                  <div className={styles.fieldHeader}>
                    <label className={styles.fieldLabel}>Notes (Optional)</label>
                    <span className={styles.characterCount}>
                      {formData.user_notes.length} / 500 characters
                    </span>
                  </div>

                  <Textarea
                    value={formData.user_notes}
                    onChange={(e) => setFormData(prev => ({ ...prev, user_notes: e.target.value.slice(0, 500) }))}
                    placeholder="e.g., 'records for john', 'urgent - deadline Friday', 'follow-up to case #123'..."
                    className={styles.notesTextarea}
                    rows={3}
                  />

                  <div className={styles.fieldHint}>
                    <div className={styles.hintText}>
                      Add notes to help organize and filter your requests later. These notes are for your reference only.
                    </div>
                  </div>
                </div>



              </CardContent>
            </Card>
  
            
            {/* Submit Buttons */}
            <div className={styles.submitSection}>
              {editingDraft ? (
                <div className={styles.editActions}>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditingDraft(null)
                      resetForm()
                    }}
                    disabled={isSubmitting}
                    className={styles.cancelButton}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleUpdateDraft}
                    disabled={isSubmitting || availablePortals.length === 0}
                    className={styles.updateButton}
                  >
                    {isSubmitting ? (
                      <>
                        <RefreshCw className={styles.spinningIcon} />
                        Updating...
                      </>
                    ) : (
                      <>
                        <Save className={styles.buttonIcon} />
                        Update Draft
                      </>
                    )}
                  </Button>
                </div>
              ) : (
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
                        <Save className={styles.buttonIcon} />
                        Save Draft
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
                        Submitting...
                      </>
                    ) : (
                      <>
                        <Send className={styles.buttonIcon} />
                        Submit Now
                      </>
                    )}
                  </Button>
                </div>
              )}
            </div>
          </div>
  
          {/* Right Column - Queue Management */}
          <div className={styles.sidebarColumn}>
            <Card className={styles.queueCard}>
              <CardHeader className={styles.cardHeader}>
                <CardTitle className={styles.cardTitle}>
                  <Clock className={styles.titleIcon} />
                  Draft Queue
                  {draftSubmissions.length > 0 && (
                    <Badge className={styles.queueBadge}>
                      {draftSubmissions.length}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className={styles.cardContent}>
                {draftSubmissions.length === 0 ? (
                  <div className={styles.emptyQueue}>
                    <p className={styles.emptyText}>No drafts saved</p>
                  </div>
                ) : (
                  <>
                    {/* Bulk Actions */}
                    {selectedDrafts.length > 0 && (
                      <div className={styles.bulkActions}>
                        <div className={styles.bulkInfo}>
                          <span className={styles.bulkCount}>
                            {selectedDrafts.length} selected
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
                              Submitting...
                            </>
                          ) : (
                            <>
                              <Play className={styles.buttonIcon} />
                              Submit All
                            </>
                          )}
                        </Button>
                      </div>
                    )}
  
                    {/* Draft List */}
                    <div className={styles.queueList}>
                      {draftSubmissions.map((draft) => (
                        <div key={draft.id} className={styles.queueItem}>
                          <div className={styles.queueHeader}>
                            <div className={styles.queueCheckbox}>
                              <Checkbox
                                checked={selectedDrafts.includes(draft.id)}
                                onCheckedChange={(checked) => {
                                  if (checked) {
                                    setSelectedDrafts(prev => [...prev, draft.id])
                                  } else {
                                    setSelectedDrafts(prev => prev.filter(id => id !== draft.id))
                                  }
                                }}
                              />
                            </div>
                            <div className={styles.queueTitleSection}>
                              <span className={styles.queueTitle}>
                                {draft.request_topic || 'Untitled Request'}
                              </span>
                              <Badge className={styles[getStatusColor(draft.status)]}>
                                {draft.status.toUpperCase()}
                              </Badge>
                            </div>
                          </div>
                          
                          <div className={styles.queueDetails}>
                            <span className={styles.queueAgency}>{draft.agency_name}</span>
                            <Badge className={styles[getPriorityColor(draft.priority)]}>
                              {getPriorityLabel(draft.priority)}
                            </Badge>
                          </div>
                          
                          <div className={styles.queuePreview}>
                            {draft.request_text.substring(0, 100)}...
                          </div>

                          {draft.user_notes && (
                            <div className={styles.queueNotes}>
                              <FileText className={styles.notesIcon} />
                              <span className={styles.notesText}>{draft.user_notes}</span>
                            </div>
                          )}

                          <div className={styles.queueFooter}>
                            <div className={styles.queueDate}>
                              {new Date(draft.created_at).toLocaleDateString()}
                              {draft.updated_at !== draft.created_at && (
                                <span className={styles.updatedIndicator}>
                                  (edited {new Date(draft.updated_at).toLocaleDateString()})
                                </span>
                              )}
                            </div>
                            
                            <div className={styles.queueActions}>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleEditDraft(draft)}
                                className={styles.editDraftButton}
                              >
                                <Edit3 className={styles.actionIcon} />
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleSubmitDraft(draft.id)}
                                className={styles.submitDraftButton}
                              >
                                <Send className={styles.actionIcon} />
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleDeleteDraft(draft.id)}
                                className={styles.deleteDraftButton}
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
  
            {/* Pending Submissions */}
            {pendingSubmissions.length > 0 && (
              <Card className={styles.queueCard}>
                <CardHeader className={styles.cardHeader}>
                  <CardTitle className={styles.cardTitle}>
                    <RefreshCw className={styles.titleIcon} />
                    Processing Queue
                    <Badge className={styles.queueBadge}>
                      {pendingSubmissions.length}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className={styles.cardContent}>
                  <div className={styles.queueList}>
                    {pendingSubmissions.map((submission) => (
                      <div key={submission.id} className={styles.queueItem}>
                        <div className={styles.queueHeader}>
                          <div className={styles.queueTitleSection}>
                            <span className={styles.queueTitle}>
                              {submission.request_topic || 'Untitled Request'}
                            </span>
                            <Badge className={styles[getStatusColor(submission.status)]}>
                              {submission.status.toUpperCase()}
                            </Badge>
                          </div>
                        </div>
                        
                        <div className={styles.queueDetails}>
                          <span className={styles.queueAgency}>{submission.agency_name}</span>
                          <Badge className={styles[getPriorityColor(submission.priority)]}>
                            {getPriorityLabel(submission.priority)}
                          </Badge>
                        </div>
                        
                        <div className={styles.queueDate}>
                          Submitted {new Date(submission.created_at).toLocaleDateString()}
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
      ) : (
        <SubmissionStatusTab
          currentUserId={currentUserId}
          onViewRequestDetail={onViewRequestDetail}
        />
      )}
    </div>
  )
}