import {describe,expect,it} from 'vitest'
import {renderMarkdown} from './markdown'

function parse(source:string){return new DOMParser().parseFromString(source,'text/html').body}
describe('Markdown rendering security',()=>{
  it('renders real Markdown structure while blocking raw HTML and active links',()=>{
    const output=parse(renderMarkdown('# 标题\n\n**加粗**\n\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[危险链接](javascript:alert(1))'))
    expect(output.querySelector('h1')?.textContent).toBe('标题')
    expect(output.querySelector('strong')?.textContent).toBe('加粗')
    expect(output.querySelector('script,[onerror],a[href^="javascript:"]')).toBeNull()
  })
  it('does not let attachment filenames inject links or attributes',()=>{
    const id='f7b273ca-25f4-47bf-b1b7-010781746c61'
    const output=parse(renderMarkdown(`[[asset:${id}]]`,[{id,filename:'x](javascript:alert(1))<img onerror=alert(2)>',contentType:'image/png',size:10,url:'javascript:alert(3)'}]))
    expect(output.querySelector('img')?.getAttribute('src')).toBe(`/api/media/${id}`)
    expect(output.querySelector('script,[onerror],a[href^="javascript:"]')).toBeNull()
  })
  it('sanitizes unsafe preview protocols and keeps code samples as text',()=>{
    const id='f7b273ca-25f4-47bf-b1b7-010781746c61'
    const html=renderMarkdown(`[[asset:${id}]]\n\n\`\`\`html\n<svg onload=alert(1)>\n\`\`\``,[{id,filename:'file.pdf',contentType:'application/pdf',size:10,url:'/api/media/'+id}],{[id]:'javascript:alert(1)'})
    const output=parse(html)
    expect(output.querySelector('a[href^="javascript:"],svg,[onload]')).toBeNull()
    expect(output.querySelector('pre code')?.textContent).toContain('<svg onload=alert(1)>')
  })
})
