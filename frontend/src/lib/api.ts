// API client for FOIA Agent Dashboard
// Connects to Flask bridge server

import { Request, MessageDraft } from '@/types/requests'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ApiResponse<T = Record<string, unknown>> {
  success: boolean
  error?: string
  data?: T
  [key: string]: unknown
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  private async request<T = Record<string, unknown>>(
    endpoint: string, 
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`
      
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      })

      const data: unknown = await response.json()
      
      return {
        success: response.ok && (data as { success?: boolean }).success !== false,
        ...(data as Record<string, unknown>)
      }
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error)
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Network error'
      }
    }
  }

  // Request endpoints
  async getFlaggedRequests(): Promise<ApiResponse<{ requests: Request[], count: number }>> {
    return this.request('/api/requests/flagged')
  }

  // Draft endpoints
  async generateDraft(requestId: string): Promise<ApiResponse<{ 
    draft: MessageDraft, 
    draft_id: string, 
    request_number: string 
  }>> {
    return this.request('/api/drafts/generate', {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId })
    })
  }

  async sendDraft(draftId: string): Promise<ApiResponse<{ 
    message: string, 
    draft_id: string, 
    request_number: string 
  }>> {
    return this.request(`/api/drafts/${draftId}/send`, {
      method: 'POST'
    })
  }

  async skipDraft(draftId: string, reason?: string): Promise<ApiResponse<{ 
    message: string, 
    draft_id: string 
  }>> {
    return this.request(`/api/drafts/${draftId}/skip`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    })
  }

  async editDraft(draftId: string, content: { 
    subject: string; 
    message: string 
  }): Promise<ApiResponse<{ 
    draft: MessageDraft, 
    draft_id: string 
  }>> {
    return this.request(`/api/drafts/${draftId}/edit`, {
      method: 'PUT',
      body: JSON.stringify(content)
    })
  }

  // Health check
  async healthCheck(): Promise<ApiResponse<{ status: string, timestamp: string, service: string }>> {
    return this.request('/health')
  }
}

// Export singleton instance
export const api = new ApiClient()

// Export types for use in components
export type { ApiResponse }