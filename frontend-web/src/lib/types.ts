export type Role = 'admin' | 'editor' | 'viewer'
export interface User { id: number; email: string; role: Role; permissions: string[] }
export interface Attachment { id: string; filename: string; contentType: string; size: number; url: string }
export interface Post { id: number; title: string; summary: string; category: string; status: 'draft' | 'published'; readMinutes: number; views: number; likes: number; createdAt: string; updatedAt: string; content?: string; attachments?: Attachment[] }
export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }
export interface AuthResult { access_token: string; token_type: string; expires_in: number; user: User }
export interface AdminRoute { name: string; path: string; component: string; title: string; permission: string; hidden?: boolean }
