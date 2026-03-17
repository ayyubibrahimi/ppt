// src/components/ui/LoadingStates.tsx

import React from 'react'
import { RefreshCw, Loader2 } from 'lucide-react'
import styles from './LoadingStates.module.scss'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

interface SkeletonProps {
  variant?: 'text' | 'card' | 'list' | 'button' | 'avatar'
  lines?: number
  className?: string
}

interface PlaceholderProps {
  type: 'requests' | 'drafts' | 'overview'
  count?: number
}

// Basic spinner component
export const Spinner: React.FC<SpinnerProps> = ({ 
  size = 'md', 
  className = '' 
}) => {
  return (
    <div className={`${styles.spinner} ${styles[`spinner--${size}`]} ${className}`}>
      <Loader2 className={styles.spinnerIcon} />
    </div>
  )
}

// Refresh spinner for buttons
export const RefreshSpinner: React.FC<SpinnerProps> = ({ 
  size = 'md', 
  className = '' 
}) => {
  return (
    <RefreshCw className={`${styles.refreshSpinner} ${styles[`spinner--${size}`]} ${className}`} />
  )
}

// Skeleton loading components
export const Skeleton: React.FC<SkeletonProps> = ({ 
  variant = 'text', 
  lines = 1, 
  className = '' 
}) => {
  if (variant === 'text') {
    return (
      <div className={`${styles.skeletonContainer} ${className}`}>
        {Array.from({ length: lines }).map((_, index) => (
          <div 
            key={index} 
            className={`${styles.skeleton} ${styles.skeletonText} ${
              index === lines - 1 ? styles.skeletonTextLast : ''
            }`} 
          />
        ))}
      </div>
    )
  }

  if (variant === 'card') {
    return (
      <div className={`${styles.skeletonCard} ${className}`}>
        <div className={styles.skeletonCardHeader}>
          <div className={`${styles.skeleton} ${styles.skeletonAvatar}`} />
          <div className={styles.skeletonCardTitle}>
            <div className={`${styles.skeleton} ${styles.skeletonText}`} />
            <div className={`${styles.skeleton} ${styles.skeletonText} ${styles.skeletonTextSmall}`} />
          </div>
        </div>
        <div className={styles.skeletonCardBody}>
          <div className={`${styles.skeleton} ${styles.skeletonText}`} />
          <div className={`${styles.skeleton} ${styles.skeletonText}`} />
          <div className={`${styles.skeleton} ${styles.skeletonText} ${styles.skeletonTextLast}`} />
        </div>
      </div>
    )
  }

  if (variant === 'button') {
    return (
      <div className={`${styles.skeleton} ${styles.skeletonButton} ${className}`} />
    )
  }

  if (variant === 'avatar') {
    return (
      <div className={`${styles.skeleton} ${styles.skeletonAvatar} ${className}`} />
    )
  }

  // Default list variant
  return (
    <div className={`${styles.skeletonList} ${className}`}>
      <div className={`${styles.skeleton} ${styles.skeletonListItem}`} />
      <div className={`${styles.skeleton} ${styles.skeletonListItem}`} />
      <div className={`${styles.skeleton} ${styles.skeletonListItem} ${styles.skeletonListItemLast}`} />
    </div>
  )
}

// Specialized placeholders for different sections
export const RequestsPlaceholder: React.FC<PlaceholderProps> = ({ 
  type, 
  count = 3 
}) => {
  if (type === 'overview') {
    return (
      <div className={styles.overviewPlaceholder}>
        <div className={styles.overviewStats}>
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className={styles.statCard}>
              <div className={`${styles.skeleton} ${styles.skeletonStatNumber}`} />
              <div className={`${styles.skeleton} ${styles.skeletonStatLabel}`} />
            </div>
          ))}
        </div>
        <div className={styles.overviewChart}>
          <div className={`${styles.skeleton} ${styles.skeletonChart}`} />
        </div>
      </div>
    )
  }

  if (type === 'requests') {
    return (
      <div className={styles.requestsPlaceholder}>
        {Array.from({ length: count }).map((_, index) => (
          <div key={index} className={styles.requestCard}>
            <div className={styles.requestCardHeader}>
              <div className={`${styles.skeleton} ${styles.skeletonRequestNumber}`} />
              <div className={`${styles.skeleton} ${styles.skeletonPriority}`} />
            </div>
            <div className={styles.requestCardBody}>
              <div className={`${styles.skeleton} ${styles.skeletonText}`} />
              <div className={`${styles.skeleton} ${styles.skeletonText} ${styles.skeletonTextSmall}`} />
            </div>
            <div className={styles.requestCardFooter}>
              <div className={`${styles.skeleton} ${styles.skeletonDate}`} />
              <div className={`${styles.skeleton} ${styles.skeletonStatus}`} />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (type === 'drafts') {
    return (
      <div className={styles.draftsPlaceholder}>
        <div className={styles.draftHeader}>
          <div className={`${styles.skeleton} ${styles.skeletonDraftTitle}`} />
          <div className={`${styles.skeleton} ${styles.skeletonButton}`} />
        </div>
        <div className={styles.draftBody}>
          <div className={`${styles.skeleton} ${styles.skeletonInput}`} />
          <div className={`${styles.skeleton} ${styles.skeletonTextarea}`} />
        </div>
        <div className={styles.draftActions}>
          <div className={`${styles.skeleton} ${styles.skeletonButton}`} />
          <div className={`${styles.skeleton} ${styles.skeletonButton}`} />
        </div>
      </div>
    )
  }

  return null
}

// Loading overlay for full components
export const LoadingOverlay: React.FC<{ 
  isVisible: boolean
  message?: string
  children: React.ReactNode 
}> = ({ 
  isVisible, 
  message = 'Loading...', 
  children 
}) => {
  return (
    <div className={styles.loadingContainer}>
      {children}
      {isVisible && (
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingContent}>
            <Spinner size="lg" />
            <p className={styles.loadingMessage}>{message}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// Inline loading states for buttons
export const ButtonSpinner: React.FC<{ isLoading: boolean; children: React.ReactNode }> = ({ 
  isLoading, 
  children 
}) => {
  return (
    <>
      {isLoading && <Spinner size="sm" className={styles.buttonSpinner} />}
      {children}
    </>
  )
}