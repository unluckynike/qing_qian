/**
 * 轻量富文本渲染(安全):
 * 先把 HTML 特殊字符全部转义(防注入),再格式化模型输出里常见的少量 Markdown:
 * **加粗**、*斜体*、`代码`、# 标题(渲染为加粗)、换行 → <br>。
 * 列表保持纯文本行(配合提示词"用 1. 2. 的普通文本"),不做复杂块级解析。
 */
export function renderRichText(input: string): string {
  if (!input) return ''
  const escaped = input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/^#{1,4}\s+(.+)$/gm, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}
