'use client'

import { useState, useMemo } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import styles from './FilterSidebar.module.scss'
import { Request } from '@/types/requests'

interface FilterSidebarProps {
  requests: Request[]
  selectedCategories: string[]
  onCategoriesChange: (categories: string[]) => void
  selectedPortals: string[]
  onPortalsChange: (portals: string[]) => void
  selectedLifecycleStates: string[]
  onLifecycleStatesChange: (states: string[]) => void
  selectedActionTypes: string[]
  onActionTypesChange: (types: string[]) => void
  hasDocumentsFilter: boolean | null
  onHasDocumentsChange: (value: boolean | null) => void
}

export default function FilterSidebar({
  requests,
  selectedCategories,
  onCategoriesChange,
  selectedPortals,
  onPortalsChange,
  selectedLifecycleStates,
  onLifecycleStatesChange,
  selectedActionTypes,
  onActionTypesChange,
  hasDocumentsFilter,
  onHasDocumentsChange
}: FilterSidebarProps) {
  const [categorySearch, setCategorySearch] = useState('')

  // Extract unique categories with counts
  const categoryStats = useMemo(() => {
    const stats = new Map<string, number>()

    requests.forEach(request => {
      if (request.user_notes && request.user_notes.trim()) {
        const note = request.user_notes.trim()
        stats.set(note, (stats.get(note) || 0) + 1)
      }
    })

    // Convert to array and sort by count (descending), then alphabetically
    return Array.from(stats.entries())
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count
        return a.category.localeCompare(b.category)
      })
  }, [requests])

  // Filter categories based on search
  const filteredCategories = useMemo(() => {
    if (!categorySearch.trim()) return categoryStats

    const searchLower = categorySearch.toLowerCase()
    return categoryStats.filter(({ category }) =>
      category.toLowerCase().includes(searchLower)
    )
  }, [categoryStats, categorySearch])

  // Extract unique portals
  const uniquePortals = useMemo(() => {
    return [...new Set(requests.map(r => r.portal_name))].filter(Boolean).sort()
  }, [requests])

  // Lifecycle states
  const lifecycleStates = ['active', 'closed', 'complete']

  // Action types
  const actionTypes = [
    { value: 'user_action', label: 'User Action' },
    { value: 'agent_action', label: 'Agent Action' },
    { value: 'no_action', label: 'No Action' }
  ]

  const toggleCategory = (category: string) => {
    if (selectedCategories.includes(category)) {
      onCategoriesChange(selectedCategories.filter(c => c !== category))
    } else {
      onCategoriesChange([...selectedCategories, category])
    }
  }


  const toggleLifecycleState = (state: string) => {
    if (selectedLifecycleStates.includes(state)) {
      onLifecycleStatesChange(selectedLifecycleStates.filter(s => s !== state))
    } else {
      onLifecycleStatesChange([...selectedLifecycleStates, state])
    }
  }

  const toggleActionType = (type: string) => {
    if (selectedActionTypes.includes(type)) {
      onActionTypesChange(selectedActionTypes.filter(t => t !== type))
    } else {
      onActionTypesChange([...selectedActionTypes, type])
    }
  }

  const clearAllFilters = () => {
    onCategoriesChange([])
    onPortalsChange([])
    onLifecycleStatesChange([])
    onActionTypesChange([])
    onHasDocumentsChange(null)
  }

  const hasActiveFilters = selectedCategories.length > 0 ||
    selectedPortals.length > 0 ||
    selectedLifecycleStates.length > 0 ||
    selectedActionTypes.length > 0 ||
    hasDocumentsFilter !== null

  return (
    <div className={styles.sidebar}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTitle}>FILTERS</div>
        {hasActiveFilters && (
          <button onClick={clearAllFilters} className={styles.clearButton}>
            <X className={styles.clearIcon} />
            CLEAR
          </button>
        )}
      </div>

      {/* Top Filters - Compact */}
      <div className={styles.topFilters}>
        {/* Portal Filter */}
        <div className={styles.filterGroup}>
          <div className={styles.filterLabel}>PORTAL</div>
          <div className={styles.portalSelectContainer}>
            <select
              className={styles.portalSelect}
              value={selectedPortals[0] || ''}
              onChange={(e) => {
                if (e.target.value) {
                  onPortalsChange([e.target.value])
                } else {
                  onPortalsChange([])
                }
              }}
            >
              <option value="">All Portals ({uniquePortals.length})</option>
              {uniquePortals.map(portal => (
                <option key={portal} value={portal}>
                  {portal}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Lifecycle Filter */}
        <div className={styles.filterGroup}>
          <div className={styles.filterLabel}>LIFECYCLE</div>
          <div className={styles.filterChips}>
            {lifecycleStates.map(state => (
              <button
                key={state}
                onClick={() => toggleLifecycleState(state)}
                className={`${styles.chip} ${selectedLifecycleStates.includes(state) ? styles.chipActive : ''}`}
              >
                {state.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Action Type Filter */}
        <div className={styles.filterGroup}>
          <div className={styles.filterLabel}>ACTION</div>
          <div className={styles.filterChips}>
            {actionTypes.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => toggleActionType(value)}
                className={`${styles.chip} ${selectedActionTypes.includes(value) ? styles.chipActive : ''}`}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Request Categories Section */}
      <div className={styles.categoriesSection}>
        <div className={styles.categoriesHeader}>
          <div className={styles.categoriesTitle}>REQUEST CATEGORIES</div>
          <div className={styles.categoriesCount}>{categoryStats.length}</div>
        </div>

        {/* Search Input */}
        <div className={styles.searchContainer}>
          <Search className={styles.searchIcon} />
          <Input
            value={categorySearch}
            onChange={(e) => setCategorySearch(e.target.value)}
            placeholder="search categories..."
            className={styles.searchInput}
          />
        </div>

        {/* Categories List */}
        <div className={styles.categoriesList}>
          {filteredCategories.length === 0 ? (
            <div className={styles.emptyState}>
              {categorySearch ? 'no matching categories' : 'no categories yet'}
            </div>
          ) : (
            filteredCategories.map(({ category, count }) => (
              <div
                key={category}
                className={`${styles.categoryItem} ${
                  selectedCategories.includes(category) ? styles.categoryItemActive : ''
                }`}
                onClick={() => toggleCategory(category)}
              >
                <Checkbox
                  checked={selectedCategories.includes(category)}
                  onCheckedChange={() => toggleCategory(category)}
                  className={styles.categoryCheckbox}
                />
                <div className={styles.categoryLabel}>{category}</div>
                <div className={styles.categoryCount}>{count}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
