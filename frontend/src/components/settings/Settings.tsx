'use client'

import GoogleDriveConnection from './GoogleDriveConnection'

export default function Settings({ currentUserId }: { currentUserId?: string }) {
  return (
    <div className="p-8 space-y-6">
      <GoogleDriveConnection />
    </div>
  )
}