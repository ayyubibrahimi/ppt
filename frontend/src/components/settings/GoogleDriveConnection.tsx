'use client'

import { useState, useEffect } from 'react'
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Check, X, CloudIcon } from 'lucide-react'

export default function GoogleDriveConnection() {
  const supabase = createClientComponentClient()
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  useEffect(() => {
    checkConnectionStatus()
    
    // Check for OAuth callback results
    const params = new URLSearchParams(window.location.search)
    
    if (params.get('drive_connected') === 'true') {
      setIsConnected(true)
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname)
    }
    
    if (params.get('drive_error')) {
      const errorType = params.get('drive_error')
      setError(
        errorType === 'denied' 
          ? 'You denied access to Google Drive'
          : 'Failed to connect to Google Drive. Please try again.'
      )
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])
  
  async function checkConnectionStatus() {
    try {
      const { data: { user } } = await supabase.auth.getUser()
      
      if (!user) {
        setIsLoading(false)
        return
      }
      
      const { data: userData } = await supabase
        .from('users')
        .select('google_drive_enabled')
        .eq('id', user.id)
        .single()
      
      setIsConnected(userData?.google_drive_enabled || false)
    } catch (err) {
      console.error('Failed to check connection status:', err)
    } finally {
      setIsLoading(false)
    }
  }
  
  async function handleConnect() {
    setIsConnecting(true)
    setError(null)
    
    // Redirect to OAuth flow
    window.location.href = '/api/auth/google'
  }
  
  async function handleDisconnect() {
    if (!confirm('Are you sure you want to disconnect Google Drive?')) {
      return
    }
    
    setIsConnecting(true)
    setError(null)
    
    try {
      const response = await fetch('/api/auth/google/disconnect', {
        method: 'POST',
      })
      
      if (!response.ok) {
        throw new Error('Failed to disconnect')
      }
      
      setIsConnected(false)
    } catch (err) {
      setError('Failed to disconnect. Please try again.')
    } finally {
      setIsConnecting(false)
    }
  }
  
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Google Drive</CardTitle>
          <CardDescription>Loading...</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CloudIcon className="h-5 w-5" />
          Google Drive Integration
        </CardTitle>
        <CardDescription>
          Connect your Google Drive to automatically save downloaded documents
        </CardDescription>
      </CardHeader>
      
      <CardContent>
        <div className="space-y-4">
          {/* Connection Status */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center gap-3">
              {isConnected ? (
                <Check className="h-5 w-5 text-green-500" />
              ) : (
                <X className="h-5 w-5 text-gray-400" />
              )}
              <div>
                <p className="font-medium">
                  {isConnected ? 'Connected' : 'Not Connected'}
                </p>
                <p className="text-sm text-gray-500">
                  {isConnected 
                    ? 'Documents will automatically upload to your Google Drive'
                    : 'Connect to enable automatic document uploads'
                  }
                </p>
              </div>
            </div>
            
            {isConnected ? (
              <Button
                variant="outline"
                onClick={handleDisconnect}
                disabled={isConnecting}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                onClick={handleConnect}
                disabled={isConnecting}
              >
                {isConnecting ? 'Connecting...' : 'Connect Google Drive'}
              </Button>
            )}
          </div>
          
          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
            </div>
          )}
          
          {/* Info */}
          {!isConnected && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
              <p className="font-medium mb-1">What happens when you connect:</p>
              <ul className="list-disc list-inside space-y-1 ml-2">
                <li>You will see a Google popup asking for permission</li>
                <li>We can only access files we create (not your existing files)</li>
                <li>Documents are organized in folders by request number</li>
                <li>You can disconnect anytime</li>
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}