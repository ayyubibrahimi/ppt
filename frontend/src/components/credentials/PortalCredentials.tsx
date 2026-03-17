  'use client'

  import { useState, useEffect } from 'react'
  import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
  import { Plus, Edit3, Trash2, Shield, CheckCircle, AlertCircle, RefreshCw, Eye, EyeOff, Key, User, MapPin } from 'lucide-react'
  import { Button } from '@/components/ui/button'
  import { Input } from '@/components/ui/input'
  import { Badge } from '@/components/ui/badge'
  import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
  import { Textarea } from '@/components/ui/textarea'
  import styles from './PortalCredentials.module.scss'

  // Types
  interface Portal {
    id: string
    agency_name: string
    portal_url: string
    portal_type: string
    is_active: boolean
  }

  interface UserPortalCredential {
    id: string
    user_id: string
    portal_id: string
    is_active: boolean
    verification_status: 'untested' | 'verified' | 'failed' | 'expired'
    last_verified: string | null
    last_used: string | null
    usage_count: number
    created_at: string
    updated_at: string
    // Contact information for requests
    requester_name?: string
    requester_email?: string
    requester_phone?: string
    requester_organization?: string
    street_address?: string
    city?: string
    state?: string
    zip_code?: string
    preferred_department?: 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other'
    // From the view join
    agency_name: string
    portal_url: string
    portal_type: string
    display_status: string
    days_since_verification: number | null
  }

  interface CredentialFormData {
    portal_id: string
    username: string
    password: string
    // Contact information
    requester_name: string
    requester_email: string
    requester_phone: string
    requester_organization: string
    street_address: string
    city: string
    state: string
    zip_code: string
    preferred_department: 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other' | ''
  }

  interface PortalCredentialsProps {
    currentUserId?: string
  }

  // US States for dropdown
  const US_STATES = [
    { value: 'AL', label: 'Alabama' },
    { value: 'AK', label: 'Alaska' },
    { value: 'AZ', label: 'Arizona' },
    { value: 'AR', label: 'Arkansas' },
    { value: 'CA', label: 'California' },
    { value: 'CO', label: 'Colorado' },
    { value: 'CT', label: 'Connecticut' },
    { value: 'DE', label: 'Delaware' },
    { value: 'FL', label: 'Florida' },
    { value: 'GA', label: 'Georgia' },
    { value: 'HI', label: 'Hawaii' },
    { value: 'ID', label: 'Idaho' },
    { value: 'IL', label: 'Illinois' },
    { value: 'IN', label: 'Indiana' },
    { value: 'IA', label: 'Iowa' },
    { value: 'KS', label: 'Kansas' },
    { value: 'KY', label: 'Kentucky' },
    { value: 'LA', label: 'Louisiana' },
    { value: 'ME', label: 'Maine' },
    { value: 'MD', label: 'Maryland' },
    { value: 'MA', label: 'Massachusetts' },
    { value: 'MI', label: 'Michigan' },
    { value: 'MN', label: 'Minnesota' },
    { value: 'MS', label: 'Mississippi' },
    { value: 'MO', label: 'Missouri' },
    { value: 'MT', label: 'Montana' },
    { value: 'NE', label: 'Nebraska' },
    { value: 'NV', label: 'Nevada' },
    { value: 'NH', label: 'New Hampshire' },
    { value: 'NJ', label: 'New Jersey' },
    { value: 'NM', label: 'New Mexico' },
    { value: 'NY', label: 'New York' },
    { value: 'NC', label: 'North Carolina' },
    { value: 'ND', label: 'North Dakota' },
    { value: 'OH', label: 'Ohio' },
    { value: 'OK', label: 'Oklahoma' },
    { value: 'OR', label: 'Oregon' },
    { value: 'PA', label: 'Pennsylvania' },
    { value: 'RI', label: 'Rhode Island' },
    { value: 'SC', label: 'South Carolina' },
    { value: 'SD', label: 'South Dakota' },
    { value: 'TN', label: 'Tennessee' },
    { value: 'TX', label: 'Texas' },
    { value: 'UT', label: 'Utah' },
    { value: 'VT', label: 'Vermont' },
    { value: 'VA', label: 'Virginia' },
    { value: 'WA', label: 'Washington' },
    { value: 'WV', label: 'West Virginia' },
    { value: 'WI', label: 'Wisconsin' },
    { value: 'WY', label: 'Wyoming' }
  ]

  export default function PortalCredentials({ currentUserId }: PortalCredentialsProps) {
    const supabase = createClientComponentClient()
    
    // Use the passed currentUserId or fallback to hardcoded test ID
    const userId = currentUserId 
    
    // State
    const [credentials, setCredentials] = useState<UserPortalCredential[]>([])
    const [availablePortals, setAvailablePortals] = useState<Portal[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    // Sub-tab state
    const [activeTab, setActiveTab] = useState<'list' | 'add'>('list')

    // Modal state (only for editing now)
    const [isEditModalOpen, setIsEditModalOpen] = useState(false)
    const [editingCredential, setEditingCredential] = useState<UserPortalCredential | null>(null)

    // Bulk add state
    const [selectedPortalIds, setSelectedPortalIds] = useState<string[]>([])
    
    // Form state
    const [formData, setFormData] = useState<CredentialFormData>({
      portal_id: '',
      username: '',
      password: '',
      requester_name: '',
      requester_email: '',
      requester_phone: '',
      requester_organization: '',
      street_address: '',
      city: '',
      state: '',
      zip_code: '',
      preferred_department: ''
    })
    const [showPassword, setShowPassword] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isVerifying, setIsVerifying] = useState<string | null>(null)
    const [activeFormSection, setActiveFormSection] = useState<'credentials' | 'contact'>('credentials')
    const [bulkAddSuccess, setBulkAddSuccess] = useState<string | null>(null)
    const [departmentFilter, setDepartmentFilter] = useState<'all' | 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other'>('all')
    const [portalTypeFilter, setPortalTypeFilter] = useState<'all' | 'email' | 'nextrequest' | 'govqa' | 'portal'>('all')

    // Load data on component mount
    useEffect(() => {
      loadCredentials()
      loadAvailablePortals()
    }, [userId])

    const loadCredentials = async () => {
      try {
        setIsLoading(true)
        setError(null)

        const { data, error } = await supabase
          .from('user_portal_credentials_summary')
          .select('*')
          .eq('user_id', userId)
          .order('agency_name')

        if (error) throw error

        setCredentials(data || [])
      } catch (err) {
        console.error('Failed to load credentials:', err)
        setError('Failed to load portal credentials')
      } finally {
        setIsLoading(false)
      }
    }

    const loadAvailablePortals = async () => {
      try {
        const { data, error } = await supabase
          .from('portals')
          .select('*')
          .eq('is_active', true)
          .order('agency_name')

        if (error) throw error

        setAvailablePortals(data || [])
      } catch (err) {
        console.error('Failed to load portals:', err)
      }
    }

    const getPortalsWithoutCredentials = () => {
      const credentialPortalIds = credentials.map(cred => cred.portal_id)
      return availablePortals.filter(portal => !credentialPortalIds.includes(portal.id))
    }

    // Infer department type from agency name
    const inferDepartmentType = (agencyName: string): 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other' => {
      const name = agencyName.toLowerCase()
      if (name.includes('police') || name.includes('pd')) {
        return 'police'
      } else if (name.includes('sheriff')) {
        return 'sheriff'
      } else if (name.includes('district attorney') || name.includes('da ') || name.includes("da's")) {
        return 'district_attorney'
      } else if (name.includes('probation')) {
        return 'probation'
      }
      return 'other'
    }

    // Bulk selection helpers
    const portalsWithoutCredentials = getPortalsWithoutCredentials()

    // Filter by portal type and department type
    let availableForBulkAdd = portalsWithoutCredentials

    // Apply portal type filter
    if (portalTypeFilter !== 'all') {
      availableForBulkAdd = availableForBulkAdd.filter(portal => portal.portal_type === portalTypeFilter)
    }

    // Apply department type filter
    if (departmentFilter !== 'all') {
      availableForBulkAdd = availableForBulkAdd.filter(portal => inferDepartmentType(portal.agency_name) === departmentFilter)
    }

    // Get counts per portal type for the filter buttons (not affected by department filter)
    const portalTypeCounts = {
      all: portalsWithoutCredentials.length,
      email: portalsWithoutCredentials.filter(p => p.portal_type === 'email').length,
      nextrequest: portalsWithoutCredentials.filter(p => p.portal_type === 'nextrequest').length,
      govqa: portalsWithoutCredentials.filter(p => p.portal_type === 'govqa').length,
      portal: portalsWithoutCredentials.filter(p => p.portal_type === 'portal').length,
    }

    // Get base portals for department counting (filtered by portal type if applicable)
    const portalsForDepartmentCounting = portalTypeFilter === 'all'
      ? portalsWithoutCredentials
      : portalsWithoutCredentials.filter(p => p.portal_type === portalTypeFilter)

    // Get counts per department type for the filter buttons (respects portal type filter)
    const departmentCounts = {
      all: portalsForDepartmentCounting.length,
      police: portalsForDepartmentCounting.filter(p => inferDepartmentType(p.agency_name) === 'police').length,
      sheriff: portalsForDepartmentCounting.filter(p => inferDepartmentType(p.agency_name) === 'sheriff').length,
      district_attorney: portalsForDepartmentCounting.filter(p => inferDepartmentType(p.agency_name) === 'district_attorney').length,
      probation: portalsForDepartmentCounting.filter(p => inferDepartmentType(p.agency_name) === 'probation').length,
      other: portalsForDepartmentCounting.filter(p => inferDepartmentType(p.agency_name) === 'other').length,
    }

    const togglePortalSelection = (portalId: string) => {
      setSelectedPortalIds(prev =>
        prev.includes(portalId)
          ? prev.filter(id => id !== portalId)
          : [...prev, portalId]
      )
    }

    const selectAllPortals = () => {
      setSelectedPortalIds(availableForBulkAdd.map(p => p.id))
    }

    const deselectAllPortals = () => {
      setSelectedPortalIds([])
    }

    const resetForm = () => {
      setFormData({
        portal_id: '',
        username: '',
        password: '',
        requester_name: '',
        requester_email: '',
        requester_phone: '',
        requester_organization: '',
        street_address: '',
        city: '',
        state: '',
        zip_code: '',
        preferred_department: ''
      })
      setSelectedPortalIds([])
      setActiveFormSection('credentials')
      setBulkAddSuccess(null)
      setDepartmentFilter('all')
      setPortalTypeFilter('all')
    }

    const handleBulkAddCredentials = async () => {
      console.log('=== DEBUG: Starting handleBulkAddCredentials ===')
      console.log('Selected portals:', selectedPortalIds)
      console.log('Current form data:', formData)
      console.log('User ID:', userId)

      // Validate portal selection
      if (selectedPortalIds.length === 0) {
        setError('Please select at least one portal')
        return
      }

      const requiredFields = [
        'username', 'password', 'requester_name',
        'requester_email', 'street_address', 'city', 'state', 'zip_code'
      ]

      const missingFields = requiredFields.filter(field => {
        const value = formData[field as keyof CredentialFormData]
        return !value || value.toString().trim() === ''
      })

      console.log('Missing fields:', missingFields)

      if (missingFields.length > 0) {
        const errorMsg = `Please fill in all required fields: ${missingFields.join(', ')}`
        console.log('Validation error:', errorMsg)
        setError(errorMsg)
        return
      }

      try {
        setIsSubmitting(true)
        setError(null)
        setBulkAddSuccess(null)

        console.log('Setting isSubmitting to true')

        // Create credential records for all selected portals
        const credentialRecords = selectedPortalIds.map(portalId => ({
          user_id: userId,
          portal_id: portalId,
          encrypted_username: formData.username.trim(),
          encrypted_password: formData.password.trim(),
          requester_name: formData.requester_name.trim(),
          requester_email: formData.requester_email.trim(),
          requester_phone: formData.requester_phone.trim() || null,
          requester_organization: formData.requester_organization.trim() || null,
          street_address: formData.street_address.trim(),
          city: formData.city.trim(),
          state: formData.state.trim(),
          zip_code: formData.zip_code.trim(),
          preferred_department: formData.preferred_department || null,
          is_active: true,
          verification_status: 'verified',
          last_verified: new Date().toISOString(),
          usage_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }))

        console.log('Credential records to insert:', credentialRecords)

        const { data, error } = await supabase
          .from('user_portal_credentials')
          .insert(credentialRecords)
          .select()

        console.log('Insert response:', { data, error })

        if (error) {
          console.error('Insert error details:', error)
          throw new Error(`Database error: ${error.message}`)
        }

        console.log('Insert successful, data:', data)

        const count = selectedPortalIds.length
        setBulkAddSuccess(`Successfully added credentials for ${count} portal${count > 1 ? 's' : ''}`)

        // Reset form
        console.log('Resetting form')
        resetForm()

        // Reload credentials
        console.log('Reloading credentials...')
        await loadCredentials()

        // Switch to list tab after short delay to show success message
        setTimeout(() => {
          setActiveTab('list')
          setBulkAddSuccess(null)
        }, 2000)

        console.log('=== SUCCESS: Credentials added successfully ===')

      } catch (err) {
        console.error('=== ERROR: Failed to add credentials ===', err)
        setError(`Failed to add portal credentials: ${err instanceof Error ? err.message : 'Unknown error'}`)
      } finally {
        console.log('Setting isSubmitting to false')
        setIsSubmitting(false)
      }
    }

    const handleEditCredential = async () => {
      if (!editingCredential) return

      const requiredFields = [
        'username', 'password', 'requester_name', 
        'requester_email', 'street_address', 'city', 'state', 'zip_code'
      ]
      
      const missingFields = requiredFields.filter(field => !formData[field as keyof CredentialFormData])
      
      if (missingFields.length > 0) {
        setError(`Please fill in all required fields: ${missingFields.join(', ')}`)
        return
      }

      try {
        setIsSubmitting(true)
        setError(null)

        const updateData = {
          encrypted_username: formData.username, // TODO: Encrypt in production
          encrypted_password: formData.password, // TODO: Encrypt in production
          requester_name: formData.requester_name,
          requester_email: formData.requester_email,
          requester_phone: formData.requester_phone,
          requester_organization: formData.requester_organization,
          street_address: formData.street_address,
          city: formData.city,
          state: formData.state,
          zip_code: formData.zip_code,
          preferred_department: formData.preferred_department || null,
          verification_status: 'untested' // Reset verification when credentials change
        }

        const { error } = await supabase
          .from('user_portal_credentials')
          .update(updateData)
          .eq('id', editingCredential.id)

        if (error) throw error

        // Reset form and close modal
        resetForm()
        setIsEditModalOpen(false)
        setEditingCredential(null)
        
        // Reload credentials
        await loadCredentials()

      } catch (err) {
        console.error('Failed to update credential:', err)
        setError('Failed to update portal credentials')
      } finally {
        setIsSubmitting(false)
      }
    }

    const handleDeleteCredential = async (credentialId: string) => {
      if (!confirm('Are you sure you want to delete these credentials?')) return

      try {
        setError(null)

        const { error } = await supabase
          .from('user_portal_credentials')
          .delete()
          .eq('id', credentialId)

        if (error) throw error

        // Reload credentials
        await loadCredentials()

      } catch (err) {
        console.error('Failed to delete credential:', err)
        setError('Failed to delete portal credentials')
      }
    }

    const handleVerifyCredential = async (credentialId: string) => {
      // TODO: Implement actual credential verification
      // For now, just simulate verification
      setIsVerifying(credentialId)
      
      setTimeout(async () => {
        try {
          const { error } = await supabase
            .from('user_portal_credentials')
            .update({
              verification_status: 'verified',
              last_verified: new Date().toISOString()
            })
            .eq('id', credentialId)

          if (error) throw error
          await loadCredentials()
        } catch (err) {
          console.error('Failed to update verification:', err)
        } finally {
          setIsVerifying(null)
        }
      }, 2000)
    }

    const getStatusColor = (status: string) => {
      switch (status) {
        case 'Verified': return 'statusVerified'
        case 'Needs Re-verification': return 'statusWarning'
        case 'Failed Verification': return 'statusFailed'
        case 'Not Tested': return 'statusUntested'
        case 'Disabled': return 'statusDisabled'
        default: return 'statusDefault'
      }
    }

    const getPortalTypeColor = (type: string) => {
      switch (type) {
        case 'nextrequest': return 'typeNextRequest'
        case 'govqa': return 'typeGovQA'
        case 'granicus': return 'typeGranicus'
        default: return 'typeDefault'
      }
    }

    const openEditModal = (credential: UserPortalCredential) => {
      setEditingCredential(credential)
      setFormData({
        portal_id: credential.portal_id,
        username: '', // Don't pre-fill for security
        password: '', // Don't pre-fill for security
        requester_name: credential.requester_name || '',
        requester_email: credential.requester_email || '',
        requester_phone: credential.requester_phone || '',
        requester_organization: credential.requester_organization || '',
        street_address: credential.street_address || '',
        city: credential.city || '',
        state: credential.state || '',
        zip_code: credential.zip_code || '',
        preferred_department: credential.preferred_department || ''
      })
      setActiveFormSection('credentials')
      setIsEditModalOpen(true)
    }

    // Render form section for edit modal only
    const renderEditFormSection = () => {
      if (activeFormSection === 'credentials') {
        return (
          <>
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Username *</label>
              <Input
                type="text"
                value={formData.username}
                onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
                placeholder="Enter your portal username"
                className={styles.fieldInput}
              />
            </div>

            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Password *</label>
              <div className={styles.passwordField}>
                <Input
                  type={showPassword ? "text" : "password"}
                  value={formData.password}
                  onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
                  placeholder="Enter your portal password"
                  className={styles.passwordInput}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowPassword(!showPassword)}
                  className={styles.passwordToggle}
                >
                  {showPassword ? <EyeOff className={styles.eyeIcon} /> : <Eye className={styles.eyeIcon} />}
                </Button>
              </div>
            </div>
          </>
        )
      }

      return (
        <>
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Full Name *</label>
              <Input
                type="text"
                value={formData.requester_name}
                onChange={(e) => setFormData(prev => ({ ...prev, requester_name: e.target.value }))}
                placeholder="Your full name"
                className={styles.fieldInput}
              />
            </div>
            
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Email Address *</label>
              <Input
                type="email"
                value={formData.requester_email}
                onChange={(e) => setFormData(prev => ({ ...prev, requester_email: e.target.value }))}
                placeholder="your.email@example.com"
                className={styles.fieldInput}
              />
            </div>
          </div>

          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Phone Number</label>
              <Input
                type="tel"
                value={formData.requester_phone}
                onChange={(e) => setFormData(prev => ({ ...prev, requester_phone: e.target.value }))}
                placeholder="(555) 123-4567"
                className={styles.fieldInput}
              />
            </div>
            
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>Organization</label>
              <Input
                type="text"
                value={formData.requester_organization}
                onChange={(e) => setFormData(prev => ({ ...prev, requester_organization: e.target.value }))}
                placeholder="Your organization (optional)"
                className={styles.fieldInput}
              />
            </div>
          </div>

          <div className={styles.formField}>
            <label className={styles.fieldLabel}>Street Address *</label>
            <Textarea
              value={formData.street_address}
              onChange={(e) => setFormData(prev => ({ ...prev, street_address: e.target.value }))}
              placeholder="1234 Main Street, Apt 567"
              className={styles.fieldInput}
              rows={2}
            />
          </div>

          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>City *</label>
              <Input
                type="text"
                value={formData.city}
                onChange={(e) => setFormData(prev => ({ ...prev, city: e.target.value }))}
                placeholder="City name"
                className={styles.fieldInput}
              />
            </div>
            
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>State *</label>
              <Select 
                value={formData.state} 
                onValueChange={(value) => setFormData(prev => ({ ...prev, state: value }))}
              >
                <SelectTrigger className={styles.fieldInput}>
                  <SelectValue placeholder="Select state..." />
                </SelectTrigger>
                <SelectContent>
                  {US_STATES.map((state) => (
                    <SelectItem key={state.value} value={state.value}>
                      {state.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className={styles.formField}>
              <label className={styles.fieldLabel}>ZIP Code *</label>
              <Input
                type="text"
                value={formData.zip_code}
                onChange={(e) => setFormData(prev => ({ ...prev, zip_code: e.target.value.replace(/\D/g, '').slice(0, 5) }))}
                placeholder="12345"
                className={styles.fieldInput}
                maxLength={5}
              />
            </div>
          </div>

          <div className={styles.formField}>
            <label className={styles.fieldLabel}>Preferred Department</label>
            <Select 
              value={formData.preferred_department} 
              onValueChange={(value) => setFormData(prev => ({ 
                ...prev, 
                preferred_department: value as 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other' 
              }))}
            >
              <SelectTrigger className={styles.fieldInput}>
                <SelectValue placeholder="Select department type..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="police">Police Department</SelectItem>
                <SelectItem value="sheriff">Sheriffs Office</SelectItem>
                <SelectItem value="district_attorney">District Attorney</SelectItem>
                <SelectItem value="probation">Probation Department</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
            <p className={styles.fieldHint}>
              Choose the type of department you typically request from at this portal
            </p>
          </div>
        </>
      )
    }

    return (
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerContent}>
            <div className={styles.headerLeft}>
              <div className={styles.headerIcon}>
                <Shield className={styles.icon} />
              </div>
              <div className={styles.headerText}>
                <h1 className={styles.title}>PORTAL CREDENTIALS</h1>
                <p className={styles.subtitle}>
                  Manage your login credentials and contact information for public records portals
                </p>
              </div>
            </div>
            
            <div className={styles.headerRight}>
              <div className={styles.headerStats}>
                <div className={styles.stat}>
                  <span className={styles.statNumber}>{credentials.length}</span>
                  <span className={styles.statLabel}>Configured</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statNumber}>
                    {credentials.filter(c => c.verification_status === 'verified').length}
                  </span>
                  <span className={styles.statLabel}>Verified</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className={styles.errorBanner}>
            <div className={styles.errorContent}>
              <AlertCircle className={styles.errorIcon} />
              <p className={styles.errorText}>{error}</p>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setError(null)}
                className={styles.errorDismiss}
              >
                ×
              </Button>
            </div>
          </div>
        )}

        {/* Sub-tab Navigation */}
        <div className={styles.subTabNav}>
          <button
            type="button"
            onClick={() => { setActiveTab('list'); resetForm(); }}
            className={`${styles.subTab} ${activeTab === 'list' ? styles.subTabActive : ''}`}
          >
            <Shield className={styles.subTabIcon} />
            My Credentials
            {credentials.length > 0 && (
              <span className={styles.subTabBadge}>{credentials.length}</span>
            )}
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('add'); setActiveFormSection('credentials'); }}
            className={`${styles.subTab} ${activeTab === 'add' ? styles.subTabActive : ''}`}
          >
            <Plus className={styles.subTabIcon} />
            Add Credentials
            {availableForBulkAdd.length > 0 && (
              <span className={styles.subTabBadge}>{availableForBulkAdd.length} available</span>
            )}
          </button>
        </div>

        {/* Success Banner */}
        {bulkAddSuccess && (
          <div className={styles.successBanner}>
            <div className={styles.successContent}>
              <CheckCircle className={styles.successIcon} />
              <p className={styles.successText}>{bulkAddSuccess}</p>
            </div>
          </div>
        )}

        {/* Main Content */}
        <div className={styles.mainContent}>
          {isLoading ? (
            <div className={styles.loadingState}>
              <RefreshCw className={styles.loadingIcon} />
              <p className={styles.loadingText}>Loading portal credentials...</p>
            </div>
          ) : activeTab === 'list' ? (
            /* List Tab Content */
            credentials.length === 0 ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyContent}>
                  <Key className={styles.emptyIcon} />
                  <h3 className={styles.emptyTitle}>No Portal Credentials</h3>
                  <p className={styles.emptyText}>
                    Add your login credentials and contact information for public records portals to start submitting requests.
                  </p>
                  <Button
                    className={styles.emptyButton}
                    onClick={() => setActiveTab('add')}
                  >
                    <Plus className={styles.actionIcon} />
                    Add Your First Credentials
                  </Button>
                </div>
              </div>
            ) : (
              <div className={styles.credentialsGrid}>
                {credentials.map((credential) => (
                  <div key={credential.id} className={styles.credentialCard}>
                    <div className={styles.cardHeader}>
                      <div className={styles.cardTitle}>
                        <h3 className={styles.agencyName}>{credential.agency_name}</h3>
                        <div className={styles.cardBadges}>
                          <Badge className={styles[getPortalTypeColor(credential.portal_type)]}>
                            {credential.portal_type.toUpperCase()}
                          </Badge>
                          <Badge className={styles[getStatusColor(credential.display_status)]}>
                            {credential.display_status}
                          </Badge>
                        </div>
                      </div>

                      <div className={styles.cardActions}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleVerifyCredential(credential.id)}
                          disabled={isVerifying === credential.id}
                          className={styles.verifyButton}
                        >
                          {isVerifying === credential.id ? (
                            <RefreshCw className={styles.spinningIcon} />
                          ) : (
                            <CheckCircle className={styles.actionIcon} />
                          )}
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditModal(credential)}
                          className={styles.editButton}
                        >
                          <Edit3 className={styles.actionIcon} />
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteCredential(credential.id)}
                          className={styles.deleteButton}
                        >
                          <Trash2 className={styles.actionIcon} />
                        </Button>
                      </div>
                    </div>

                    <div className={styles.cardContent}>
                      <div className={styles.cardDetail}>
                        <span className={styles.detailLabel}>Portal URL:</span>
                        <span className={styles.detailValue}>{credential.portal_url}</span>
                      </div>

                      {credential.requester_name && (
                        <div className={styles.cardDetail}>
                          <span className={styles.detailLabel}>Requester:</span>
                          <span className={styles.detailValue}>
                            {credential.requester_name}
                            {credential.requester_organization && ` (${credential.requester_organization})`}
                          </span>
                        </div>
                      )}

                      {credential.city && credential.state && (
                        <div className={styles.cardDetail}>
                          <span className={styles.detailLabel}>Location:</span>
                          <span className={styles.detailValue}>
                            {credential.city}, {credential.state} {credential.zip_code}
                          </span>
                        </div>
                      )}

                      {credential.preferred_department && (
                        <div className={styles.cardDetail}>
                          <span className={styles.detailLabel}>Department:</span>
                          <span className={styles.detailValue}>
                            {credential.preferred_department === 'police' ? 'Police Department' :
                            credential.preferred_department === 'sheriff' ? "Sheriff's Office" :
                            credential.preferred_department === 'district_attorney' ? 'District Attorney' :
                            credential.preferred_department === 'probation' ? 'Probation Department' : 'Other'}
                          </span>
                        </div>
                      )}

                      {credential.last_verified && (
                        <div className={styles.cardDetail}>
                          <span className={styles.detailLabel}>Last Verified:</span>
                          <span className={styles.detailValue}>
                            {new Date(credential.last_verified).toLocaleDateString()}
                            {credential.days_since_verification && (
                              <span className={styles.daysAgo}>
                                ({credential.days_since_verification} days ago)
                              </span>
                            )}
                          </span>
                        </div>
                      )}

                      {credential.usage_count > 0 && (
                        <div className={styles.cardDetail}>
                          <span className={styles.detailLabel}>Times Used:</span>
                          <span className={styles.detailValue}>{credential.usage_count}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            /* Add Tab Content - Bulk Add Form */
            <div className={styles.bulkAddContainer}>
              {availableForBulkAdd.length === 0 ? (
                <div className={styles.emptyState}>
                  <div className={styles.emptyContent}>
                    <CheckCircle className={styles.emptyIcon} />
                    <h3 className={styles.emptyTitle}>All Portals Configured</h3>
                    <p className={styles.emptyText}>
                      You have already added credentials for all available portals.
                    </p>
                    <Button
                      className={styles.emptyButton}
                      onClick={() => setActiveTab('list')}
                    >
                      View My Credentials
                    </Button>
                  </div>
                </div>
              ) : (
                <div className={styles.bulkAddForm}>
                  {/* Portal Selection Section */}
                  {activeFormSection === 'credentials' && (
                    <>
                      <div className={styles.formSection}>
                        <div className={styles.sectionHeader}>
                          <h3 className={styles.sectionTitle}>Select Portals</h3>
                          <div className={styles.selectionActions}>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={selectAllPortals}
                              disabled={selectedPortalIds.length === availableForBulkAdd.length || availableForBulkAdd.length === 0}
                            >
                              Select All
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={deselectAllPortals}
                              disabled={selectedPortalIds.length === 0}
                            >
                              Deselect All
                            </Button>
                          </div>
                        </div>
                        <p className={styles.sectionDescription}>
                          Choose the portals you want to add credentials for. The same username, password, and contact information will be used for all selected portals.
                        </p>

                        {/* Portal Type Filter */}
                        <div className={styles.departmentFilter}>
                          <span className={styles.filterLabel}>Filter by portal type:</span>
                          <div className={styles.filterButtons}>
                            <button
                              type="button"
                              onClick={() => { setPortalTypeFilter('all'); setSelectedPortalIds([]); }}
                              className={`${styles.filterButton} ${portalTypeFilter === 'all' ? styles.filterButtonActive : ''}`}
                            >
                              All Types ({portalTypeCounts.all})
                            </button>
                            {portalTypeCounts.email > 0 && (
                              <button
                                type="button"
                                onClick={() => { setPortalTypeFilter('email'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${portalTypeFilter === 'email' ? styles.filterButtonActive : ''}`}
                              >
                                Email ({portalTypeCounts.email})
                              </button>
                            )}
                            {portalTypeCounts.nextrequest > 0 && (
                              <button
                                type="button"
                                onClick={() => { setPortalTypeFilter('nextrequest'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${portalTypeFilter === 'nextrequest' ? styles.filterButtonActive : ''}`}
                              >
                                NextRequest ({portalTypeCounts.nextrequest})
                              </button>
                            )}
                            {portalTypeCounts.govqa > 0 && (
                              <button
                                type="button"
                                onClick={() => { setPortalTypeFilter('govqa'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${portalTypeFilter === 'govqa' ? styles.filterButtonActive : ''}`}
                              >
                                GovQA ({portalTypeCounts.govqa})
                              </button>
                            )}
                            {portalTypeCounts.portal > 0 && (
                              <button
                                type="button"
                                onClick={() => { setPortalTypeFilter('portal'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${portalTypeFilter === 'portal' ? styles.filterButtonActive : ''}`}
                              >
                                Other ({portalTypeCounts.portal})
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Department Type Filter */}
                        <div className={styles.departmentFilter}>
                          <span className={styles.filterLabel}>Filter by department:</span>
                          <div className={styles.filterButtons}>
                            <button
                              type="button"
                              onClick={() => { setDepartmentFilter('all'); setSelectedPortalIds([]); }}
                              className={`${styles.filterButton} ${departmentFilter === 'all' ? styles.filterButtonActive : ''}`}
                            >
                              All ({departmentCounts.all})
                            </button>
                            {departmentCounts.police > 0 && (
                              <button
                                type="button"
                                onClick={() => { setDepartmentFilter('police'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${departmentFilter === 'police' ? styles.filterButtonActive : ''}`}
                              >
                                Police ({departmentCounts.police})
                              </button>
                            )}
                            {departmentCounts.sheriff > 0 && (
                              <button
                                type="button"
                                onClick={() => { setDepartmentFilter('sheriff'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${departmentFilter === 'sheriff' ? styles.filterButtonActive : ''}`}
                              >
                                Sheriff ({departmentCounts.sheriff})
                              </button>
                            )}
                            {departmentCounts.district_attorney > 0 && (
                              <button
                                type="button"
                                onClick={() => { setDepartmentFilter('district_attorney'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${departmentFilter === 'district_attorney' ? styles.filterButtonActive : ''}`}
                              >
                                District Attorney ({departmentCounts.district_attorney})
                              </button>
                            )}
                            {departmentCounts.probation > 0 && (
                              <button
                                type="button"
                                onClick={() => { setDepartmentFilter('probation'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${departmentFilter === 'probation' ? styles.filterButtonActive : ''}`}
                              >
                                Probation ({departmentCounts.probation})
                              </button>
                            )}
                            {departmentCounts.other > 0 && (
                              <button
                                type="button"
                                onClick={() => { setDepartmentFilter('other'); setSelectedPortalIds([]); }}
                                className={`${styles.filterButton} ${departmentFilter === 'other' ? styles.filterButtonActive : ''}`}
                              >
                                Other ({departmentCounts.other})
                              </button>
                            )}
                          </div>
                        </div>

                        <div className={styles.portalGrid}>
                          {availableForBulkAdd.map((portal) => (
                            <label
                              key={portal.id}
                              className={`${styles.portalCheckbox} ${selectedPortalIds.includes(portal.id) ? styles.portalChecked : ''}`}
                            >
                              <input
                                type="checkbox"
                                checked={selectedPortalIds.includes(portal.id)}
                                onChange={() => togglePortalSelection(portal.id)}
                                className={styles.checkbox}
                              />
                              <div className={styles.portalInfo}>
                                <span className={styles.portalName}>{portal.agency_name}</span>
                                <Badge className={styles[getPortalTypeColor(portal.portal_type)]}>
                                  {portal.portal_type.toUpperCase()}
                                </Badge>
                              </div>
                            </label>
                          ))}
                        </div>

                        {selectedPortalIds.length > 0 && (
                          <p className={styles.selectionCount}>
                            {selectedPortalIds.length} portal{selectedPortalIds.length !== 1 ? 's' : ''} selected
                          </p>
                        )}
                      </div>

                      <div className={styles.formSection}>
                        <h3 className={styles.sectionTitle}>Login Credentials</h3>
                        <p className={styles.sectionDescription}>
                          Enter the username and password that will be used for all selected portals.
                        </p>

                        <div className={styles.formField}>
                          <label className={styles.fieldLabel}>Username *</label>
                          <Input
                            type="text"
                            value={formData.username}
                            onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
                            placeholder="Enter your portal username"
                            className={styles.fieldInput}
                          />
                        </div>

                        <div className={styles.formField}>
                          <label className={styles.fieldLabel}>Password *</label>
                          <div className={styles.passwordField}>
                            <Input
                              type={showPassword ? "text" : "password"}
                              value={formData.password}
                              onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
                              placeholder="Enter your portal password"
                              className={styles.passwordInput}
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => setShowPassword(!showPassword)}
                              className={styles.passwordToggle}
                            >
                              {showPassword ? <EyeOff className={styles.eyeIcon} /> : <Eye className={styles.eyeIcon} />}
                            </Button>
                          </div>
                        </div>
                      </div>

                      <div className={styles.formActions}>
                        <Button
                          onClick={() => setActiveFormSection('contact')}
                          disabled={selectedPortalIds.length === 0 || !formData.username || !formData.password}
                          className={styles.nextButton}
                        >
                          Next: Contact Info
                          <MapPin className={styles.actionIcon} />
                        </Button>
                      </div>
                    </>
                  )}

                  {/* Contact Information Section */}
                  {activeFormSection === 'contact' && (
                    <>
                      <div className={styles.formSection}>
                        <h3 className={styles.sectionTitle}>Contact Information</h3>
                        <p className={styles.sectionDescription}>
                          This information will be used when submitting requests to the {selectedPortalIds.length} selected portal{selectedPortalIds.length !== 1 ? 's' : ''}.
                        </p>

                        <div className={styles.formRow}>
                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>Full Name *</label>
                            <Input
                              type="text"
                              value={formData.requester_name}
                              onChange={(e) => setFormData(prev => ({ ...prev, requester_name: e.target.value }))}
                              placeholder="Your full name"
                              className={styles.fieldInput}
                            />
                          </div>

                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>Email Address *</label>
                            <Input
                              type="email"
                              value={formData.requester_email}
                              onChange={(e) => setFormData(prev => ({ ...prev, requester_email: e.target.value }))}
                              placeholder="your.email@example.com"
                              className={styles.fieldInput}
                            />
                          </div>
                        </div>

                        <div className={styles.formRow}>
                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>Phone Number</label>
                            <Input
                              type="tel"
                              value={formData.requester_phone}
                              onChange={(e) => setFormData(prev => ({ ...prev, requester_phone: e.target.value }))}
                              placeholder="(555) 123-4567"
                              className={styles.fieldInput}
                            />
                          </div>

                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>Organization</label>
                            <Input
                              type="text"
                              value={formData.requester_organization}
                              onChange={(e) => setFormData(prev => ({ ...prev, requester_organization: e.target.value }))}
                              placeholder="Your organization (optional)"
                              className={styles.fieldInput}
                            />
                          </div>
                        </div>

                        <div className={styles.formField}>
                          <label className={styles.fieldLabel}>Street Address *</label>
                          <Textarea
                            value={formData.street_address}
                            onChange={(e) => setFormData(prev => ({ ...prev, street_address: e.target.value }))}
                            placeholder="1234 Main Street, Apt 567"
                            className={styles.fieldInput}
                            rows={2}
                          />
                        </div>

                        <div className={styles.formRow}>
                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>City *</label>
                            <Input
                              type="text"
                              value={formData.city}
                              onChange={(e) => setFormData(prev => ({ ...prev, city: e.target.value }))}
                              placeholder="City name"
                              className={styles.fieldInput}
                            />
                          </div>

                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>State *</label>
                            <Select
                              value={formData.state}
                              onValueChange={(value) => setFormData(prev => ({ ...prev, state: value }))}
                            >
                              <SelectTrigger className={styles.fieldInput}>
                                <SelectValue placeholder="Select state..." />
                              </SelectTrigger>
                              <SelectContent>
                                {US_STATES.map((state) => (
                                  <SelectItem key={state.value} value={state.value}>
                                    {state.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>

                          <div className={styles.formField}>
                            <label className={styles.fieldLabel}>ZIP Code *</label>
                            <Input
                              type="text"
                              value={formData.zip_code}
                              onChange={(e) => setFormData(prev => ({ ...prev, zip_code: e.target.value.replace(/\D/g, '').slice(0, 5) }))}
                              placeholder="12345"
                              className={styles.fieldInput}
                              maxLength={5}
                            />
                          </div>
                        </div>

                        <div className={styles.formField}>
                          <label className={styles.fieldLabel}>Preferred Department</label>
                          <Select
                            value={formData.preferred_department}
                            onValueChange={(value) => setFormData(prev => ({
                              ...prev,
                              preferred_department: value as 'police' | 'sheriff' | 'district_attorney' | 'probation' | 'other'
                            }))}
                          >
                            <SelectTrigger className={styles.fieldInput}>
                              <SelectValue placeholder="Select department type..." />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="police">Police Department</SelectItem>
                              <SelectItem value="sheriff">Sheriffs Office</SelectItem>
                              <SelectItem value="district_attorney">District Attorney</SelectItem>
                              <SelectItem value="probation">Probation Department</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                          <p className={styles.fieldHint}>
                            Choose the type of department you typically request from
                          </p>
                        </div>
                      </div>

                      <div className={styles.formActions}>
                        <Button
                          variant="outline"
                          onClick={() => setActiveFormSection('credentials')}
                          className={styles.backButton}
                        >
                          Back
                        </Button>
                        <Button
                          onClick={handleBulkAddCredentials}
                          disabled={isSubmitting || !formData.requester_name || !formData.requester_email || !formData.street_address || !formData.city || !formData.state || !formData.zip_code}
                          className={styles.saveButton}
                        >
                          {isSubmitting ? (
                            <>
                              <RefreshCw className={styles.spinningIcon} />
                              Adding...
                            </>
                          ) : (
                            <>
                              <Plus className={styles.actionIcon} />
                              Add Credentials for {selectedPortalIds.length} Portal{selectedPortalIds.length !== 1 ? 's' : ''}
                            </>
                          )}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Edit Credential Modal */}
        <Dialog open={isEditModalOpen} onOpenChange={(open) => {
          setIsEditModalOpen(open)
          if (!open) {
            resetForm()
            setEditingCredential(null)
          }
        }}>
          <DialogContent className={styles.modal}>
            <DialogHeader>
              <DialogTitle className={styles.modalTitle}>
                Edit Credentials - {editingCredential?.agency_name}
              </DialogTitle>
            </DialogHeader>
            
            <div className={styles.modalContent}>
              {/* Section Navigation */}
              <div className={styles.formSectionNav}>
                <button
                  type="button"
                  onClick={() => setActiveFormSection('credentials')}
                  className={`${styles.sectionTab} ${activeFormSection === 'credentials' ? styles.sectionTabActive : ''}`}
                >
                  <Key className={styles.sectionIcon} />
                  Login Credentials
                </button>
                <button
                  type="button"
                  onClick={() => setActiveFormSection('contact')}
                  className={`${styles.sectionTab} ${activeFormSection === 'contact' ? styles.sectionTabActive : ''}`}
                >
                  <User className={styles.sectionIcon} />
                  Contact Information
                </button>
              </div>

              {/* Form Fields */}
              {renderEditFormSection()}
              
              <div className={styles.modalActions}>
                <Button
                  variant="outline"
                  onClick={() => setIsEditModalOpen(false)}
                  disabled={isSubmitting}
                  className={styles.cancelButton}
                >
                  Cancel
                </Button>
                
                {activeFormSection === 'credentials' && (
                  <Button
                    onClick={() => setActiveFormSection('contact')}
                    disabled={!formData.username || !formData.password}
                    className={styles.nextButton}
                  >
                    Next: Contact Info
                    <MapPin className={styles.actionIcon} />
                  </Button>
                )}
                
                {activeFormSection === 'contact' && (
                  <>
                    <Button
                      variant="outline"
                      onClick={() => setActiveFormSection('credentials')}
                      className={styles.backButton}
                    >
                      Back
                    </Button>
                    <Button
                      onClick={handleEditCredential}
                      disabled={isSubmitting || !formData.requester_name || !formData.requester_email || !formData.street_address || !formData.city || !formData.state || !formData.zip_code}
                      className={styles.saveButton}
                    >
                      {isSubmitting ? (
                        <>
                          <RefreshCw className={styles.spinningIcon} />
                          Updating...
                        </>
                      ) : (
                        <>
                          <Edit3 className={styles.actionIcon} />
                          Update Credentials
                        </>
                      )}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    )
  }