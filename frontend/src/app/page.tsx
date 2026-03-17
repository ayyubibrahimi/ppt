'use client'

import { useState, useEffect } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { AlertTriangle, RefreshCw, Zap, List, Bell, Eye, Key, PlusCircle, LogOut, User, Upload, AlertCircle, Mail, Database, MessageSquare, Settings as SettingsIcon, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MessageDraftService } from '@/services/MessageDraftService'
import FlaggedRequestsTab from '../components/tab/RequestsTab'
import MessageManagementTab from '../components/tab/MessageManagementTab'
import RequestDetailPage from '../components/tab/RequestDetailPage'
import PortalCredentials from '@/components/credentials/PortalCredentials'
import SubmitRequest from '@/components/submitRequests/SubmitRequest'
import Settings from '@/components/settings/Settings'
import About from '@/components/about/About'
import AuthPage from '@/components/auth/AuthPage'
import BulkAnalysis from '../components/BulkAnalysis/BulkAnalysis'
import styles from './AttentionQueuePage.module.scss'
import { Request, MessageDraft, RequestDetailData, UserProfile } from '@/types/requests'

interface AuthState {
  user: { id: string; email?: string; user_metadata?: { full_name?: string; phone?: string; organization?: string } } | null  // ✅ Proper typing
  userProfile: UserProfile | null
  isLoading: boolean
  isAuthenticated: boolean
}

interface PageState {
  // Data
  requests: Request[]
  selectedRequest: Request | null
  selectedRequestDrafts: MessageDraft[]
  requestDetailData: RequestDetailData | null

  // UI State
  activeView: 'requests' | 'portal-credentials' | 'submit-request' | 'bulk-analysis' | 'settings' | 'about'
  activeTab: 'requests' | 'detail' | 'messages'
  isLoadingRequests: boolean
  isLoadingDrafts: boolean
  isLoadingDetail: boolean
  error: string | null
  lastUpdated: string | null

  // Actions in progress
  isApprovingDraft: boolean
  isGeneratingDraft: boolean
}

export default function AttentionQueuePage() {
  const supabase = createClientComponentClient()
  
  // Authentication state
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    userProfile: null,
    isLoading: true,
    isAuthenticated: false
  })
  
  // App state
  const [state, setState] = useState<PageState>({
    requests: [],
    selectedRequest: null,
    selectedRequestDrafts: [],
    requestDetailData: null,
    activeView: 'requests',
    activeTab: 'requests',
    isLoadingRequests: false,
    isLoadingDrafts: false,
    isLoadingDetail: false,
    error: null,
    lastUpdated: null,
    isApprovingDraft: false,
    isGeneratingDraft: false
  })

  // Check authentication status on mount
useEffect(() => {
  let isInitialMount = true

  checkAuthStatus()

  // Listen for auth changes
  const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
    console.log('Auth state change:', event)

    // Ignore INITIAL_SESSION events to prevent duplicate processing on mount
    if (event === 'INITIAL_SESSION' && isInitialMount) {
      isInitialMount = false
      return
    }

    // Use setTimeout to prevent deadlock with Supabase auth processing
    setTimeout(async () => {
      if (event === 'SIGNED_IN' && session?.user) {
        await handleAuthSuccess(session.user)
      } else if (event === 'SIGNED_OUT') {
        console.log('SIGNED_OUT event detected, updating auth state')
        setAuthState({
          user: null,
          userProfile: null,
          isLoading: false,
          isAuthenticated: false
        })
      } else if (event === 'TOKEN_REFRESHED') {
        // Don't trigger full auth flow on token refresh - just update the user object if needed
        console.log('Token refreshed, skipping full auth flow')
      }
    }, 0)
  })

  return () => subscription.unsubscribe()
}, [])

  // Load data when user is authenticated
  useEffect(() => {
    if (authState.isAuthenticated && authState.userProfile) {
      loadRequests()
    }
  }, [authState.isAuthenticated, authState.userProfile])

  // Load drafts when a request is selected
  useEffect(() => {
    if (state.selectedRequest && authState.userProfile) {
      loadDraftsForRequest(state.selectedRequest.id)
    } else {
      setState(prev => ({ ...prev, selectedRequestDrafts: [] }))
    }
  }, [state.selectedRequest, authState.userProfile])

  // Load detailed data when switching to detail tab
  useEffect(() => {
    if (state.activeTab === 'detail' && state.selectedRequest && !state.requestDetailData && authState.userProfile) {
      loadRequestDetailData(state.selectedRequest.id)
    }
  }, [state.activeTab, state.selectedRequest, authState.userProfile])

  /**
   * Check current authentication status
   */
  const checkAuthStatus = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      
      if (session?.user) {
        await handleAuthSuccess(session.user)
      } else {
        setAuthState({
          user: null,
          userProfile: null,
          isLoading: false,
          isAuthenticated: false
        })
      }
    } catch (error) {
      console.error('Error checking auth status:', error)
      setAuthState({
        user: null,
        userProfile: null,
        isLoading: false,
        isAuthenticated: false
      })
    }
  }

  /**
   * Handle successful authentication - supports linking to existing user records
   */
  const handleAuthSuccess = async (user: {
    id: string
    email?: string
    user_metadata?: {
      full_name?: string
      phone?: string
      organization?: string
    }
  }) => {
    try {
      console.log('=== AUTH SUCCESS DEBUG ===')
      console.log('Handling auth success for user:', user.email)
      console.log('User object:', user)

      // Check if we should skip processing (use a ref to check current state)
      let shouldSkip = false
      setAuthState(prev => {
        // If already authenticated with same user, skip processing
        if (prev.isAuthenticated && prev.user?.id === user.id) {
          console.log('User already authenticated, skipping duplicate auth success')
          shouldSkip = true
          return prev // Return unchanged state
        }
        // Otherwise, set loading state
        return { ...prev, isLoading: true }
      })

      // Exit early if we should skip
      if (shouldSkip) {
        console.log('=== END AUTH SUCCESS DEBUG (skipped) ===')
        return
      }

      let userProfile
  
      // Try to find existing user by auth ID first (most common case)
      const { data: existingUserById, error: findIdError } = await supabase
        .from('users')
        .select('*')
        .eq('id', user.id)
        .single()
  
      console.log('Existing user by ID:', existingUserById)
      console.log('Find ID error:', findIdError)
  
      if (existingUserById && !findIdError) {
        // User profile exists with this auth ID - update last login
        const { data: updatedProfile, error: updateError } = await supabase
          .from('users')
          .update({ 
            last_login: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .eq('id', user.id)
          .select()
          .single()
  
        if (updateError) {
          console.error('Error updating existing user profile:', updateError)
          throw updateError
        }
  
        userProfile = updatedProfile
        console.log('Successfully updated existing user profile by ID')
        
      } else {
        // No existing user found - create new profile
        console.log('Creating new user profile...')
        
        const { data: newProfile, error: createError } = await supabase
          .from('users')
          .insert({
            id: user.id,
            email: user.email,
            full_name: user.user_metadata?.full_name || (user.email ? user.email.split('@')[0] : 'Unknown User'), // ✅ Check if email exists first
            phone: user.user_metadata?.phone || null,
            organization: user.user_metadata?.organization || null,
            is_active: true,
            last_login: new Date().toISOString(),
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .select()
          .single()
  
        if (createError) {
          console.error('Error creating user profile:', createError)
          throw createError
        }
  
        userProfile = newProfile
        console.log('Successfully created new user profile')
      }
  
      const newAuthState = {
        user,
        userProfile,
        isLoading: false,
        isAuthenticated: true
      }
      
      console.log('Setting new auth state:', newAuthState)
      setAuthState(newAuthState)
  
      console.log('Auth success completed for user:', userProfile.email)
      console.log('=== END AUTH SUCCESS DEBUG ===')
      
    } catch (error) {
      console.error('Error handling auth success:', error)
      setAuthState({
        user: null,
        userProfile: null,
        isLoading: false,
        isAuthenticated: false
      })
    }
  }
  /**
   * Handle sign out
   */

  const handleSignOut = async () => {
    try {
      // First, update the UI state immediately to prevent any race conditions
      setAuthState({
        user: null,
        userProfile: null,
        isLoading: false,
        isAuthenticated: false
      })
      
      // Reset app state
      setState({
        requests: [],
        selectedRequest: null,
        selectedRequestDrafts: [],
        requestDetailData: null,
        activeView: 'requests',
        activeTab: 'requests',
        isLoadingRequests: false,
        isLoadingDrafts: false,
        isLoadingDetail: false,
        error: null,
        lastUpdated: null,
        isApprovingDraft: false,
        isGeneratingDraft: false
      })
      
      // Sign out from Supabase (this should handle clearing its own storage)
      await supabase.auth.signOut()
      
    } catch (error) {
      console.error('Error signing out:', error)
      // Even if signOut fails, we've already updated the UI state above
    }
  }


  /**
   * Load all requests from Supabase
   */
  const loadRequests = async () => {
    if (!authState.userProfile) return

    try {
      setState(prev => ({ ...prev, isLoadingRequests: true, error: null }))

      // Load requests with approved draft information
      const { data: requests, error } = await supabase
        .from('requests')
        .select(`
          *,
          approved_draft:message_drafts!message_drafts_request_id_fkey(
            id,
            draft_subject,
            draft_status,
            user_approved
          )
        `)
        .eq('user_id', authState.userProfile.id)
        .order('created_at', { ascending: false })

      if (error) {
        throw error
      }

      // Filter to only include approved drafts (draft_status = 'approved' AND user_approved = true AND sent_at = null)
      const requestsWithApprovedDrafts = requests?.map(request => ({
        ...request,
        approved_draft: Array.isArray(request.approved_draft)
          ? request.approved_draft.find((draft: any) =>
              draft.draft_status === 'approved' &&
              draft.user_approved === true
            )
          : null
      }))

      setState(prev => ({
        ...prev,
        requests: requestsWithApprovedDrafts || [],
        isLoadingRequests: false,
        lastUpdated: new Date().toISOString(),
        error: null
      }))

    } catch (error) {
      console.error('Failed to load requests:', error)
      setState(prev => ({
        ...prev,
        isLoadingRequests: false,
        error: 'Failed to load requests. Please try again.'
      }))
    }
  }

  /**
   * Load comprehensive request detail data
   */
  const loadRequestDetailData = async (requestId: string) => {
    try {
      setState(prev => ({ ...prev, isLoadingDetail: true, error: null }))

      // Load request details
      const { data: request, error: requestError } = await supabase
        .from('requests')
        .select('*')
        .eq('id', requestId)
        .single()

      if (requestError) throw requestError

      // Load request changes (audit trail)
      const { data: changes, error: changesError } = await supabase
        .from('request_changes')
        .select('*')
        .eq('request_id', requestId)
        .order('created_at', { ascending: false })

      if (changesError) throw changesError

      // Load message history
      const { data: messageHistory, error: messageError } = await supabase
        .from('message_drafts')
        .select('*')
        .eq('request_id', requestId)
        .order('created_at', { ascending: false })

      if (messageError) throw messageError

      // Extract additional data from latest_analysis
      const analysis = request.latest_analysis || {}
      const timelineEvents = analysis.all_timeline_events || []
      const documents = analysis.documents_available || []
      const payments = analysis.outstanding_payments || []
      const staffContact = analysis.staff_contact || ''
      const deadlines = analysis.stated_deadlines || []

      const detailData: RequestDetailData = {
        request: {
          ...request,
          request_text: request.request_text || '',
          analysis_summary: request.analysis_summary || '',
          last_portal_check: request.last_portal_check || ''
        },
        changes: changes || [],
        messageHistory: messageHistory || [],
        timelineEvents,
        documents,
        payments,
        staffContact,
        deadlines
      }

      setState(prev => ({
        ...prev,
        requestDetailData: detailData,
        isLoadingDetail: false
      }))

    } catch (error) {
      console.error('Failed to load request detail data:', error)
      setState(prev => ({
        ...prev,
        isLoadingDetail: false,
        error: 'Failed to load request details. Please try again.'
      }))
    }
  }

  /**
   * Load message drafts for a specific request
   */
  const loadDraftsForRequest = async (requestId: string) => {
    try {
      setState(prev => ({ ...prev, isLoadingDrafts: true }))

      const { data: drafts, error } = await supabase
        .from('message_drafts')
        .select('*')
        .eq('request_id', requestId)
        .order('created_at', { ascending: false })

      if (error) {
        throw error
      }

      setState(prev => ({
        ...prev,
        selectedRequestDrafts: drafts || [],
        isLoadingDrafts: false
      }))

    } catch (error) {
      console.error('Failed to load drafts:', error)
      setState(prev => ({
        ...prev,
        isLoadingDrafts: false,
        error: 'Failed to load message drafts'
      }))
    }
  }

  const refreshDrafts = async () => {
    if (state.selectedRequest) {
      await loadDraftsForRequest(state.selectedRequest.id)
    }
  }

  /**
   * Handle sidebar view change
   */
  const handleViewChange = (view: 'requests' | 'portal-credentials' | 'submit-request' | 'bulk-analysis' | 'settings' | 'about') => {
    setState(prev => ({
      ...prev,
      activeView: view,
      activeTab: 'requests',
      selectedRequest: null,
      requestDetailData: null,
      error: null
    }))
  }
  

  const handleRequestSelect = (request: Request) => {
    setState(prev => ({
      ...prev,
      selectedRequest: request,
      requestDetailData: null,
      error: null
    }))
  }

  const handleTabChange = (tab: 'requests' | 'detail' | 'messages') => {
    setState(prev => {
      if ((tab === 'detail' || tab === 'messages') && !prev.selectedRequest && prev.requests.length > 0) {
        const firstRequest = prev.requests[0]
        return {
          ...prev,
          activeTab: tab,
          selectedRequest: firstRequest,
          requestDetailData: null
        }
      }

      return {
        ...prev,
        activeTab: tab
      }
    })
  }

  const handleViewDetails = (request: Request) => {
    setState(prev => ({
      ...prev,
      selectedRequest: request,
      activeTab: 'detail',
      requestDetailData: null,
      error: null
    }))
  }

  /**
   * Handle navigation from submission status tab to request detail
   */
  const handleViewRequestDetailById = async (requestId: string) => {
    try {
      // Fetch the request by ID
      const { data: request, error } = await supabase
        .from('requests')
        .select('*')
        .eq('id', requestId)
        .single()

      if (error) throw error

      if (request) {
        // Switch to requests view if not already there
        setState(prev => ({
          ...prev,
          activeView: 'requests',
          activeTab: 'detail',
          selectedRequest: request,
          requestDetailData: null,
          error: null
        }))

        // Load the detail data
        await loadRequestDetailData(requestId)
      }
    } catch (error) {
      console.error('Failed to load request:', error)
      setState(prev => ({
        ...prev,
        error: 'Failed to load request details. Please try again.'
      }))
    }
  }

  const handleRefresh = () => {
    if (state.activeView === 'requests') {
      loadRequests()
    }

    if (state.activeTab === 'detail' && state.selectedRequest) {
      loadRequestDetailData(state.selectedRequest.id)
    }
  }

  /**
   * Create a new AI-enhanced message draft for the selected request
   */
  const handleGenerateDraft = async (messageType: string = 'contextual') => {
    if (!state.selectedRequest) return

    try {
      setState(prev => ({ ...prev, isGeneratingDraft: true, error: null }))

      const draftService = new MessageDraftService()

      // Check if a new draft should be generated based on request_changes
      const { shouldGenerate, reason } = await draftService.shouldGenerateNewDraft(state.selectedRequest.id)

      if (!shouldGenerate) {
        console.log('Skipping draft generation:', reason)
        // Load existing drafts instead of generating new ones
        await loadDraftsForRequest(state.selectedRequest.id)
        setState(prev => ({ ...prev, isGeneratingDraft: false }))
        return
      }

      console.log('Generating new draft:', reason)

      const parsedRequest = {
        ...state.selectedRequest,
        latest_analysis: typeof state.selectedRequest.latest_analysis === 'string'
          ? JSON.parse(state.selectedRequest.latest_analysis || '{}')
          : state.selectedRequest.latest_analysis
      }

      const result = await draftService.generateResponse({
        request: parsedRequest,
        userInput: `Please generate a ${messageType} message draft for this request.`,
        messageType
      })

      if ('error' in result) {
        throw new Error(result.error)
      }

      await loadDraftsForRequest(state.selectedRequest.id)
      setState(prev => ({ ...prev, isGeneratingDraft: false }))

    } catch (error) {
      console.error('Failed to generate draft:', error)
      setState(prev => ({
        ...prev,
        isGeneratingDraft: false,
        error: 'Failed to generate draft. Please try again.'
      }))
    }
  }

  /**
   * Approve a message draft using the service
   */
  const handleApproveDraft = async (draftId: string) => {
    try {
      setState(prev => ({ ...prev, isApprovingDraft: true, error: null }))

      const draftService = new MessageDraftService()
      const result = await draftService.approveDraft(draftId)

      if (!result.success) {
        throw new Error(result.error)
      }

      if (state.selectedRequest) {
        await loadDraftsForRequest(state.selectedRequest.id)
        // Refresh detail data to show updated message history
        if (state.activeTab === 'detail') {
          await loadRequestDetailData(state.selectedRequest.id)
        }
      }

      setState(prev => ({ ...prev, isApprovingDraft: false }))

    } catch (error) {
      console.error('Failed to approve draft:', error)
      setState(prev => ({
        ...prev,
        isApprovingDraft: false,
        error: 'Failed to approve draft. Please try again.'
      }))
    }
  }

  const handleUnapproveDraft = async (draftId: string) => {
    try {
      const draftService = new MessageDraftService()
      const result = await draftService.unapproveDraft(draftId)
  
      if (!result.success) {
        throw new Error(result.error)
      }
  
      if (state.selectedRequest) {
        await loadDraftsForRequest(state.selectedRequest.id)
      }
  
    } catch (error) {
      console.error('Failed to unapprove draft:', error)
      setState(prev => ({
        ...prev,
        error: 'Failed to unapprove draft. Please try again.'
      }))
    }
  }

  /**
   * Update draft content using the service
   */
  const handleUpdateDraft = async (draftId: string, updates: { subject?: string; message?: string }) => {
    try {
      const draftService = new MessageDraftService()
      const result = await draftService.updateDraft(draftId, updates)

      if (!result.success) {
        throw new Error(result.error)
      }

      if (state.selectedRequest) {
        await loadDraftsForRequest(state.selectedRequest.id)
        // Refresh detail data to show updated message history
        if (state.activeTab === 'detail') {
          await loadRequestDetailData(state.selectedRequest.id)
        }
      }

    } catch (error) {
      console.error('Failed to update draft:', error)
      setState(prev => ({
        ...prev,
        error: 'Failed to update draft. Please try again.'
      }))
    }
  }

  /**
   * Reject or skip a draft using the service
   */
  const handleRejectDraft = async (draftId: string, status: 'rejected' | 'skipped') => {
    try {
      const draftService = new MessageDraftService()
      const result = await draftService.rejectDraft(draftId, status)

      if (!result.success) {
        throw new Error(result.error)
      }

      if (state.selectedRequest) {
        await loadDraftsForRequest(state.selectedRequest.id)
        // Refresh detail data to show updated message history
        if (state.activeTab === 'detail') {
          await loadRequestDetailData(state.selectedRequest.id)
        }
      }

    } catch (error) {
      console.error(`Failed to ${status} draft:`, error)
      setState(prev => ({
        ...prev,
        error: `Failed to ${status} draft. Please try again.`
      }))
    }
  }

  // Show loading spinner while checking auth
  if (authState.isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingScreen}>
          <RefreshCw className={styles.loadingIcon} />
          <p className={styles.loadingText}>Loading...</p>
        </div>
      </div>
    )
  }

  // Show auth page if not authenticated
  if (!authState.isAuthenticated) {
    return <AuthPage onAuthSuccess={handleAuthSuccess} />
  }

  // Helper functions
  const shouldShowTabs = () => {
    return state.activeView === 'requests'
  }

  const getMainContentInfo = () => {
    switch (state.activeView) {
      case 'portal-credentials':
        return {
          icon: <List className={styles.icon} />,
          title: 'PORTAL CREDENTIALS',
          subtitle: 'Manage your login credentials for public records portals'
        }
      case 'submit-request':
        return {
          icon: <List className={styles.icon} />,
          title: 'SUBMIT REQUEST',
          subtitle: 'Submit public records requests to government agencies'
        }
      case 'bulk-analysis':
        return {
          icon: <Database className={styles.icon} />,
          title: 'BULK ANALYSIS',
          subtitle: 'Database population and comprehensive request analysis'
        }
      case 'requests':
        return {
          icon: <MessageSquare className={styles.icon} />,
          title: 'REQUESTS',
          subtitle: `${state.requests.length} total requests in system`
        }
      case 'settings':
        return {
          icon: <SettingsIcon className={styles.icon} />,
          title: 'SETTINGS',
          subtitle: 'Manage your account and integrations'
        }
      case 'about':
        return {
          icon: <Info className={styles.icon} />,
          title: 'ABOUT',
          subtitle: 'Learn how to use Public Data Agent'
        }
      default:
        return {
          icon: <MessageSquare className={styles.icon} />,
          title: 'REQUESTS',
          subtitle: 'Loading...'
        }
    }
  }

  const mainContentInfo = getMainContentInfo()

  // Compute current loading state based on active view/tab
  const isLoadingCurrent = state.isLoadingRequests || (state.activeTab === 'detail' && state.isLoadingDetail)

  return (
    <div className={styles.container}>
      {/* Enhanced Sidebar Navigation */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <div className={styles.sidebarLogo}>
            <span className={styles.logoText}>Public Data Agent</span>
          </div>
        </div>
        
        <nav className={styles.sidebarNav}>
          {/* Monitoring Section */}
          <div className={styles.navGroup}>
            <h3 className={styles.navGroupTitle}>Request Monitoring</h3>
            <button
              onClick={() => handleViewChange('requests')}
              className={`${styles.navItem} ${state.activeView === 'requests' ? styles.navItemActive : ''}`}
            >
              <List className={styles.navIcon} />
              <span className={styles.navLabel}>Requests</span>
              {state.requests.length > 0 && (
                <span className={styles.navBadge}>{state.requests.length}</span>
              )}
            </button>
          </div>
  
          {/* Analysis Section */}
          <div className={styles.navGroup}>
            <h3 className={styles.navGroupTitle}>Import</h3>
            <button
              onClick={() => handleViewChange('bulk-analysis')}
              className={`${styles.navItem} ${state.activeView === 'bulk-analysis' ? styles.navItemActive : ''}`}
            >
              <Upload className={styles.navIcon} />
              <span className={styles.navLabel}>Import</span>
            </button>
          </div>
  
          {/* Submission Section */}
          <div className={styles.navGroup}>
            <h3 className={styles.navGroupTitle}>Submit Requests</h3>
            <button
              onClick={() => handleViewChange('portal-credentials')}
              className={`${styles.navItem} ${state.activeView === 'portal-credentials' ? styles.navItemActive : ''}`}
            >
              <Key className={styles.navIcon} />
              <span className={styles.navLabel}>Portal Credentials</span>
            </button>
            <button
              onClick={() => handleViewChange('submit-request')}
              className={`${styles.navItem} ${state.activeView === 'submit-request' ? styles.navItemActive : ''}`}
            >
              <PlusCircle className={styles.navIcon} />
              <span className={styles.navLabel}>Submit Request</span>
            </button>
          </div>

          {/* Settings Section */}
          <div className={styles.navGroup}>
            <h3 className={styles.navGroupTitle}>Settings</h3>
            <button
                onClick={() => handleViewChange('settings')}
                className={`${styles.navItem} ${state.activeView === 'settings' ? styles.navItemActive : ''}`}
              >
                <SettingsIcon className={styles.navIcon} />
                <span className={styles.navLabel}>Settings</span>
              </button>
            <button
                onClick={() => handleViewChange('about')}
                className={`${styles.navItem} ${state.activeView === 'about' ? styles.navItemActive : ''}`}
              >
                <Info className={styles.navIcon} />
                <span className={styles.navLabel}>About</span>
              </button>
          </div>
        </nav>
        
        {/* User Profile & Sign Out */}
        <div className={styles.sidebarFooter}>
          <div className={styles.userProfile}>
            <div className={styles.userInfo}>
              <User className={styles.userIcon} />
              <div className={styles.userDetails}>
                <span className={styles.userName}>{authState.userProfile?.full_name}</span>
                <span className={styles.userEmail}>{authState.userProfile?.email}</span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSignOut}
              className={styles.signOutButton}
            >
              <LogOut className={styles.signOutIcon} />
            </Button>
          </div>
          
          <div className={styles.systemStatus}>
            <div className={styles.statusIndicator}></div>
            <span className={styles.statusText}>System Online</span>
          </div>
        </div>
      </aside>
  
      {/* Main content area */}
      <main className={styles.mainContent}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerContent}>
            <div className={styles.headerLeft}>
              <div className={styles.headerIcon}>
                {mainContentInfo.icon}
              </div>
              <div className={styles.headerText}>
                <h1 className={styles.title}>
                  {mainContentInfo.title}
                </h1>
                <p className={styles.subtitle}>
                  {mainContentInfo.subtitle}
                </p>
              </div>
            </div>
            
            <div className={styles.headerRight}>
              {state.lastUpdated && shouldShowTabs() && (
                <div className={styles.lastUpdated}>
                  Last updated: {new Date(state.lastUpdated).toLocaleTimeString()}
                </div>
              )}
              <div className={styles.headerActions}>
                <Button
                  variant="ghost"
                  size="icon"
                  className={styles.actionButton}
                >
                  <Bell className={styles.actionIcon} />
                </Button>
                {shouldShowTabs() && (
                  <Button
                    onClick={handleRefresh}
                    disabled={isLoadingCurrent}
                    className={styles.refreshButton}
                  >
                    <RefreshCw className={`${styles.actionIcon} ${isLoadingCurrent ? styles.spinning : ''}`} />
                    {isLoadingCurrent ? 'Loading...' : 'Refresh'}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
  
        {/* Navigation Tabs - Only show for request views */}
        {shouldShowTabs() && (
          <div className={styles.navigation}>
            <div className={styles.navContent}>
              <div className={styles.navBreadcrumb}>
                <span className={styles.navActive}>
                  {state.activeTab === 'requests' ? 'REQUESTS' :
                   state.activeTab === 'detail' ? 'REQUEST DETAILS' : 'MESSAGE MANAGEMENT'}
                </span>
              </div>
              
              <div className={styles.tabContainer}>
                <button
                  onClick={() => handleTabChange('requests')}
                  className={`${styles.tab} ${state.activeTab === 'requests' ? styles.tabActive : ''}`}
                >
                  <AlertCircle className={styles.tabIcon} />
                  <span className={styles.tabLabel}>REQUESTS</span>
                  {state.requests.length > 0 && (
                    <span className={styles.tabBadge}>{state.requests.length}</span>
                  )}
                </button>
                
                <button
                  onClick={() => handleTabChange('detail')}
                  className={`${styles.tab} ${state.activeTab === 'detail' ? styles.tabActive : ''}`}
                  disabled={!state.selectedRequest}
                >
                  <Eye className={styles.tabIcon} />
                  <span className={styles.tabLabel}>REQUEST DETAILS</span>
                  {state.selectedRequest && (
                    <span className={styles.tabBadge}>#{state.selectedRequest.request_number}</span>
                  )}
                </button>
                
                <button
                  onClick={() => handleTabChange('messages')}
                  className={`${styles.tab} ${state.activeTab === 'messages' ? styles.tabActive : ''}`}
                  disabled={!state.selectedRequest}
                >
                  <Mail className={styles.tabIcon} />
                  <span className={styles.tabLabel}>MESSAGE MANAGEMENT</span>
                  {state.selectedRequest && (
                    <span className={styles.tabBadge}>#{state.selectedRequest.request_number}</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
  
        {/* Error Banner */}
        {state.error && (
          <div className={styles.errorBanner}>
            <div className={styles.errorContent}>
              <AlertTriangle className={styles.errorIcon} />
              <p className={styles.errorText}>{state.error}</p>
            </div>
          </div>
        )}
  
        {/* Content */}
        <div className={styles.tabContent}>
          {/* Pass user context to child components */}
          {state.activeView === 'portal-credentials' && (
            <PortalCredentials currentUserId={authState.userProfile?.id} />
          )}
          {state.activeView === 'submit-request' && (
            <SubmitRequest
              currentUserId={authState.userProfile?.id}
              onViewRequestDetail={handleViewRequestDetailById}
            />
          )}
          {state.activeView === 'bulk-analysis' && (
            <BulkAnalysis currentUserId={authState.userProfile?.id} />
          )}

          {state.activeView === 'settings' && (
            <Settings currentUserId={authState.userProfile?.id} />
          )}

          {state.activeView === 'about' && (
            <About />
          )}

          {/* Existing tabbed content for request views */}
          {shouldShowTabs() && (
            <>
              {state.activeTab === 'requests' && (
                <FlaggedRequestsTab
                  requests={state.requests}
                  selectedRequest={state.selectedRequest}
                  onRequestSelect={handleRequestSelect}
                  isLoading={state.isLoadingRequests}
                  onSwitchToMessages={() => handleTabChange('messages')}
                  onViewDetails={handleViewDetails}
                />
              )}

              {state.activeTab === 'detail' && (
                <RequestDetailPage
                  requestDetailData={state.requestDetailData}
                  isLoading={state.isLoadingDetail}
                  onSwitchToMessages={() => handleTabChange('messages')}
                  onRefresh={() => state.selectedRequest && loadRequestDetailData(state.selectedRequest.id)}
                />
              )}

              {state.activeTab === 'messages' && (
                <MessageManagementTab
                  request={state.selectedRequest}
                  drafts={state.selectedRequestDrafts}
                  onGenerateDraft={handleGenerateDraft}
                  onApproveDraft={handleApproveDraft}
                  onUnapproveDraft={handleUnapproveDraft}
                  onUpdateDraft={handleUpdateDraft}
                  onRejectDraft={handleRejectDraft}
                  isGenerating={state.isGeneratingDraft}
                  isApproving={state.isApprovingDraft}
                  isLoadingDrafts={state.isLoadingDrafts}
                  onRequestSelect={handleRequestSelect}
                  allRequests={state.requests}
                  onRefreshDrafts={refreshDrafts}

                />
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}