import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type { Attachment } from './types'

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
export function renderMarkdown(content: string, attachments: Attachment[] = [], previews: Record<string, string> = {}): string {
  const assets = new Map(attachments.map(asset => [asset.id, asset]))
  const source = content.replace(/\[\[asset:([a-f0-9-]{36})\]\]/g, (_, id: string) => {
    const asset = assets.get(id)
    if (!asset) return '\n附件暂不可用\n'
    const label = asset.filename.replace(/[\\[\]()]/g, '\\$&')
    const url = previews[id] || `/api/media/${id}`
    return asset.contentType.startsWith('image/') ? `\n![${label}](${url})\n` : `\n[下载 ${label}](${url})\n`
  })
  return DOMPurify.sanitize(markdown.render(source), {
    USE_PROFILES: { html: true }, FORBID_TAGS: ['style', 'script', 'iframe', 'form', 'input', 'button'],
    FORBID_ATTR: ['style', 'srcdoc'],
  })
}
