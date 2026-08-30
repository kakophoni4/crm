export interface ShareLink {
  id: number
  token: string
  url: string
  has_password: boolean
  expires_at: string | null
  max_downloads: number | null
  download_count: number
  revoked_at: string | null
  created_at: string
}

export interface VaultFolderUserShare {
  id: number
  folder_id: number
  user_id: number
  user_name: string
  shared_by: number | null
  shared_by_name: string | null
  created_at: string
}

export interface VaultShareUser {
  id: number
  full_name: string
  username: string
}

export interface VaultFile {
  id: number
  file_id: number | null
  original_name: string
  mime_type: string
  size_bytes: number
  is_folder?: boolean
  parent_id?: number | null
  created_at: string
  share_links: ShareLink[]
  access?: 'owned' | 'shared' | string
  shared_by_name?: string | null
  folder_shares?: VaultFolderUserShare[]
}

export interface VaultFileList {
  items: VaultFile[]
  total: number
  can_write?: boolean
}

export interface VaultFileContent {
  id: number
  file_id: number
  original_name: string
  mime_type: string
  size_bytes: number
  editable: boolean
  content: string
}

export interface GroupChatFile {
  id: number
  group_id: number
  chat_id: number
  message_id: number
  attachment_index: number
  file_id: number | null
  original_name: string
  mime_type: string
  size_bytes: number
  direction: 'inbound' | 'outbound' | string
  sender_display_name: string
  sender_user_id: number | null
  sender_contact_id: number | null
  created_at: string
  download_path: string
  contact_name: string | null
}

export interface GroupChatFileList {
  items: GroupChatFile[]
  total: number
}

export interface GroupChatFileGroupSummary {
  group_id: number
  group_name: string
  file_count: number
}

export interface ShareLinkCreateBody {
  expires_in_hours?: number | null
  max_downloads?: number | null
  password?: string | null
}

export interface AnonymousShareResult {
  token: string
  url: string
  original_name: string
  mime_type: string
  size_bytes: number
  expires_at: string | null
  max_downloads: number | null
  has_password: boolean
}

export interface PublicShareInfo {
  original_name: string
  mime_type: string
  size_bytes: number
  has_password: boolean
  expires_at: string | null
  max_downloads: number | null
  download_count: number
  is_expired: boolean
  is_exhausted: boolean
}

export interface LargeShareInit {
  id: number
  part_size_bytes: number
  max_size_bytes: number
}

export interface LargeShareComplete {
  vault: VaultFile
  share: ShareLink
}
