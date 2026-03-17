'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Key, PlusCircle, MessageSquare, Database, CheckCircle } from 'lucide-react'
import styles from './About.module.scss'

export default function About() {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>How to Use Public Data Agent</h2>
      </div>

      <div className={styles.content}>
        <div className={styles.workflow}>
          {/* Step 1: Portal Credentials */}
          <Card className={styles.stepCard}>
            <CardHeader className={styles.stepHeader}>
              <div className={styles.stepNumber}>
                <span className={styles.number}>1</span>
              </div>
              <Key className={styles.stepIcon} />
              <CardTitle className={styles.stepTitle}>Add Portal Credentials</CardTitle>
            </CardHeader>
            <CardContent className={styles.stepContent}>
              <p className={styles.description}>
                Start by adding your login credentials for the public records portals.
                These credentials are securely encrypted and used by the automation system to
                access portals on your behalf. If you do not have a pre-existing account, the agent will create a new account using these credentials. 
              </p>
              <div className={styles.actionList}>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Navigate to <strong>Portal Credentials</strong> in the sidebar</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Click <strong>Add Credentials</strong> and enter portal login info</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Step 2: Submit Requests */}
          <Card className={styles.stepCard}>
            <CardHeader className={styles.stepHeader}>
              <div className={styles.stepNumber}>
                <span className={styles.number}>2</span>
              </div>
              <PlusCircle className={styles.stepIcon} />
              <CardTitle className={styles.stepTitle}>Submit Requests</CardTitle>
            </CardHeader>
            <CardContent className={styles.stepContent}>
              <p className={styles.description}>
                Submit new public records requests through the portal automation system.
                The agent will automatically fill out forms and submit your request, then
                monitor for updates.
              </p>
              <div className={styles.actionList}>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Go to <strong>Submit Request</strong> in the sidebar</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Select a portal and fill out request details</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Agent submits and begins monitoring automatically</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Step 3: Draft & Send Messages */}
          <Card className={styles.stepCard}>
            <CardHeader className={styles.stepHeader}>
              <div className={styles.stepNumber}>
                <span className={styles.number}>3</span>
              </div>
              <MessageSquare className={styles.stepIcon} />
              <CardTitle className={styles.stepTitle}>Draft & Send Messages</CardTitle>
            </CardHeader>
            <CardContent className={styles.stepContent}>
              <p className={styles.description}>
                When requests require attention (status updates, clarifications, or deadlines),
                they appear in the Flagged Requests.
              </p>
              <div className={styles.actionList}>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Check <strong>Flagged Requests</strong> for flagged requests</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Select a request and navigate to <strong>Message Management</strong></span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Review AI-generated drafts, edit if needed, and approve</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Approved messages are automatically sent by the agent</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Step 4: Analyze Downloaded Data */}
          <Card className={styles.stepCard}>
            <CardHeader className={styles.stepHeader}>
              <div className={styles.stepNumber}>
                <span className={styles.number}>4</span>
              </div>
              <Database className={styles.stepIcon} />
              <CardTitle className={styles.stepTitle}>Analyze Downloaded Data</CardTitle>
            </CardHeader>
            <CardContent className={styles.stepContent}>
              <p className={styles.description}>
                When documents are available for download, the agent automatically retrieves them,
                performs OCR, generates summaries, and uploads to Google Drive for your review.
              </p>
              <div className={styles.actionList}>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Documents are automatically downloaded when available</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>OCR and AI summarization applied to all documents</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>View summaries in <strong>Request Details</strong> tab</span>
                </div>
                <div className={styles.action}>
                  <CheckCircle className={styles.actionIcon} />
                  <span>Access full documents in Google Drive (if connected)</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Pro Tips */}
          <Card className={styles.tipsCard}>
            <CardHeader className={styles.tipsHeader}>
              <CardTitle className={styles.tipsTitle}>Pro Tips</CardTitle>
            </CardHeader>
            <CardContent className={styles.tipsContent}>
              <ul className={styles.tipsList}>
                <li>The agent checks for request updates automatically every few minutes</li>
                <li>You only need to approve one message draft per request at a time</li>
                <li>Use the <strong>Import</strong> feature to analyze existing requests from portals</li>
                <li>Connect Google Drive in Settings to automatically store downloaded documents</li>
                <li>Check the Flagged Requests regularly for requests needing your attention</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
