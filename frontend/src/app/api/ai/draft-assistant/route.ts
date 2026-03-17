// app/api/ai/draft-assistant/route.ts

import { NextRequest, NextResponse } from 'next/server'
import { AzureChatOpenAI } from '@langchain/openai'
import { SystemMessage, HumanMessage } from '@langchain/core/messages'
import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { config } from 'dotenv'
import { z } from "zod"

config()

const DraftAssistantResponseSchema = z.object({
  conversationResponse: z.string().describe("Your conversational response to the user"),
  proposedDraft: z.object({
    subject: z.string().describe("Email subject line or 'No draft generated' if no update needed"),
    message: z.string().describe("Email message content or 'No draft generated' if no update needed")
  }).describe("The proposed draft content")
})

interface Request {
  id: string
  request_number: string
  current_status: string
  agent_attention_reason: string | null
  agent_attention_priority: string
  latest_analysis: {
    all_timeline_events?: string[]
    documents_available?: string[]
    outstanding_payments?: string[]
    staff_contact?: string
    stated_deadlines?: string[]
    current_status: string
  }
}

interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

interface DraftConversation {
  id: string
  request_id: string
  conversation_history: ConversationMessage[]
  current_draft_subject: string
  current_draft_message: string
  message_type: string
  status: 'active' | 'completed' | 'abandoned'
  created_at: string
  updated_at: string
}

interface AIResponse {
  conversationResponse: string
  proposedDraft?: {
    subject: string
    message: string
  }
}

/**
 * Create Supabase client for server-side operations
 */
async function createSupabaseClient() {
  const cookieStore = await cookies()
  
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // The `setAll` method was called from a Server Component.
            // This can be ignored if you have middleware refreshing
            // user sessions.
          }
        },
      },
    }
  )
}

function createLLMClient() {
  return new AzureChatOpenAI({
    model: "gpt-4.1",
    temperature: 0.3,
    maxTokens: 1500,
    azureOpenAIApiKey: process.env.AZURE_OPENAI_API_KEY,
    azureOpenAIApiInstanceName: process.env.AZURE_OPENAI_INSTANCE_NAME,
    azureOpenAIApiDeploymentName: process.env.AZURE_OPENAI_DEPLOYMENT_NAME,
    azureOpenAIApiVersion: "2024-12-01-preview"
  })
}

export async function POST(request: NextRequest) {
  try {
    return await handleGenerateResponse(request)
  } catch (error) {
    console.error('Draft assistant error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

/**
 * Handle AI response generation for draft refinement
 */
async function handleGenerateResponse(request: NextRequest) {
  const body = await request.json()
  const { 
    request: foiaRequest, 
    conversationId, 
    userInput,
    messageType,
    tone 
  }: { 
    request: Request
    conversationId?: string
    userInput: string
    messageType?: string
    tone?: string
  } = body

  if (!foiaRequest || !userInput) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
  }

  try {
    let conversation: DraftConversation | null = null
    
    // Get existing conversation or create new one
    if (conversationId) {
      conversation = await getConversation(conversationId)
    }
    
    if (!conversation) {
      conversation = await createConversation(foiaRequest.id, messageType || 'status_update')
    }

    // Generate AI response
    const aiResponse = await generateResponse({
      request: foiaRequest,
      userInput,
      conversation,
      tone
    })

    if ('error' in aiResponse) {
      throw new Error(aiResponse.error)
    }

    // Create new messages
    const userMessage = createMessage('user', userInput)
    const assistantMessage = createMessage('assistant', aiResponse.conversationResponse)
    const newHistory = [...conversation.conversation_history, userMessage, assistantMessage]

    // Update conversation with new messages and draft (if provided)
    const updatedDraft = aiResponse.proposedDraft || {
      subject: conversation.current_draft_subject,
      message: conversation.current_draft_message
    }

    await updateConversation(conversation.id, {
      messages: newHistory,
      draft: updatedDraft
    })

    return NextResponse.json({
      conversationId: conversation.id,
      conversationResponse: aiResponse.conversationResponse, 
      draft: updatedDraft,
      conversationHistory: newHistory
    })

  } catch (error) {
    console.error('Failed to generate response:', error)
    return NextResponse.json({ error: 'Failed to generate response. Please try again.' }, { status: 500 })
  }
}

// ============================================================================
// CORE AI FUNCTION
// ============================================================================

interface GenerateResponseParams {
  request: Request
  userInput: string
  conversation: DraftConversation
  tone?: string
}

/**
 * Generate AI response based on user input and conversation context
 */
async function generateResponse(params: GenerateResponseParams): Promise<AIResponse | { error: string }> {
  try {
    const llm = createLLMClient()
    
    // Use structured output instead of manual JSON parsing
    const modelWithStructure = llm.withStructuredOutput(DraftAssistantResponseSchema)
    
    const prompt = buildPrompt(params)
    
    const messages = [
      new SystemMessage(prompt),
      new HumanMessage(params.userInput)
    ]

    const response = await modelWithStructure.invoke(messages)
    console.log('Structured response received:', response)
    
    // No parsing needed - response is already the correct type!
    const isConversationalOnly = response.proposedDraft.subject === "No draft generated" || 
                                 response.proposedDraft.message === "No draft generated"

    return {
      conversationResponse: response.conversationResponse,
      proposedDraft: isConversationalOnly ? undefined : response.proposedDraft
    }

  } catch (error) {
    console.error('Failed to generate AI response:', error)
    return { error: 'Failed to generate AI response' }
  }
}

/**
 * Build prompt based on conversation context
 */
function buildPrompt(params: GenerateResponseParams): string {
  const { request, conversation } = params
  const analysis = request.latest_analysis
  
  const timelineText = analysis.all_timeline_events?.map(event => `   • ${event}`).join('\n') || '   • No timeline events available'
  const documentsText = analysis.documents_available?.map(doc => `   • ${doc}`).join('\n') || '   • No documents currently available'
  const paymentsText = analysis.outstanding_payments?.map(payment => `   • ${payment}`).join('\n') || '   • No outstanding payments'
  const deadlinesText = analysis.stated_deadlines?.map(deadline => `   • ${deadline}`).join('\n') || '   • No specific deadlines mentioned'

  const conversationContext = conversation.conversation_history
    .map(msg => `${msg.role.toUpperCase()}: ${msg.content}`)
    .join('\n\n')

  const hasCurrentDraft = conversation.current_draft_subject || conversation.current_draft_message

  return `You are an AI assistant helping refine email drafts for public records requests. You can both have conversations AND update drafts.

RESPONSE APPROACH:
- Provide a conversational response in "conversationResponse"
- Include draft content in "proposedDraft" when creating or updating drafts
- Use "No draft generated" for both subject and message when responding conversationally without changes

EXAMPLES OF WHEN TO USE "No draft generated":
- User asks: "What do you think of the current draft?"
- User asks: "Should I mention the deadline?"
- User asks: "Is this tone appropriate?"
- User wants advice or discussion without draft changes

EXAMPLES OF WHEN TO PROVIDE ACTUAL DRAFT:
- User says: "Make it more urgent"
- User says: "Add a reference to the deadline"
- User says: "Make it more formal"
- User requests specific changes to content

REQUEST CONTEXT:
================================================================
📊 Request Number: ${request.request_number}
📈 Current Status: ${request.current_status}
🚨 Attention Reason: ${request.agent_attention_reason}
⏰ Priority Level: ${request.agent_attention_priority}
👤 Staff Contact: ${analysis.staff_contact || 'Not specified'}

📅 TIMELINE EVENTS:
${timelineText}

📄 DOCUMENTS AVAILABLE:
${documentsText}

💰 OUTSTANDING PAYMENTS:
${paymentsText}

⏰ STATED DEADLINES:
${deadlinesText}
================================================================

MESSAGE TYPE: ${conversation.message_type}
TONE: ${params.tone || 'professional'}

${conversationContext ? `CONVERSATION HISTORY:\n${conversationContext}\n\n` : ''}

${hasCurrentDraft ? `CURRENT DRAFT:
Subject: ${conversation.current_draft_subject}
Message: ${conversation.current_draft_message}

` : ''}

GUIDELINES:
- Feel free to ask questions, give advice, or discuss strategy without updating the draft
- When making draft changes, explain what you changed in your conversational response
- Reference the request number: ${request.request_number} when creating drafts
- Use timeline events and context to inform messages appropriately
- Maintain a ${params.tone || 'professional'} tone throughout
- Address the contact by name if available in staff_contact
- For government communications, keep professional but can add appropriate personality when requested

MESSAGE TYPE GUIDANCE:
${getMessageTypeGuidance(conversation.message_type)}`
}

// ============================================================================
// DATABASE OPERATIONS
// ============================================================================

/**
 * Get existing conversation
 */
async function getConversation(conversationId: string): Promise<DraftConversation | null> {
  try {
    const supabase = await createSupabaseClient()
    
    const { data: conversation, error } = await supabase
      .from('draft_conversations')
      .select('*')
      .eq('id', conversationId)
      .single()

    if (error || !conversation) {
      return null
    }

    return conversation
  } catch (error) {
    console.error('Failed to get conversation:', error)
    return null
  }
}

/**
 * Create new conversation
 */
async function createConversation(requestId: string, messageType: string): Promise<DraftConversation> {
  const supabase = await createSupabaseClient()
  
  const conversationData = {
    request_id: requestId,
    conversation_history: [],
    current_draft_subject: '',
    current_draft_message: '',
    message_type: messageType,
    status: 'active',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }

  const { data: conversation, error } = await supabase
    .from('draft_conversations')
    .insert(conversationData)
    .select()
    .single()

  if (error) {
    throw error
  }

  return conversation
}

/**
 * Update conversation with new messages and draft
 */
async function updateConversation(
  conversationId: string, 
  updates: { 
    messages: ConversationMessage[]
    draft: { subject: string; message: string }
  }
) {
  const supabase = await createSupabaseClient()

  const { error } = await supabase
    .from('draft_conversations')
    .update({
      conversation_history: updates.messages,
      current_draft_subject: updates.draft.subject,
      current_draft_message: updates.draft.message,
      updated_at: new Date().toISOString()
    })
    .eq('id', conversationId)

  if (error) {
    throw error
  }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Create conversation message
 */
function createMessage(role: 'user' | 'assistant', content: string): ConversationMessage {
  return {
    id: generateMessageId(),
    role,
    content,
    timestamp: new Date().toISOString()
  }
}

/**
 * Generate unique message ID
 */
function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

/**
 * Get message type guidance
 */
function getMessageTypeGuidance(messageType: string): string {
  switch (messageType) {
    case 'status_update':
      return `For status updates: Request current status, show understanding of process, ask about timeline if appropriate, acknowledge any recent activity.`
    case 'additional_info':
      return `For additional info: Offer to provide helpful clarification, show willingness to assist, reference current processing stage.`
    case 'clarification':
      return `For clarification: Ask specific questions about process or requirements, show understanding of current situation, offer to provide details.`
    case 'thank_you':
      return `For thank you: Express genuine appreciation for specific work or updates, acknowledge efforts, maintain professional gratitude.`
    default:
      return `Generate an appropriate professional follow-up message.`
  }
}