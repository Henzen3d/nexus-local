import fs from 'fs'
import path from 'path'

const src = path.resolve('src')
const files = []

function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name)
    if (e.isDirectory() && e.name !== 'adapters' && e.name !== 'i18n') walk(p)
    else if (/\.(tsx|ts)$/.test(e.name) && !e.name.includes('test-adapters') && e.name !== 'ThinkingParser.ts')
      files.push(p)
  }
}
walk(src)

const ptHints =
  /[àáâãäéêíóôõúçÀÁÂÃÉÊÍÓÔÕÚÇ]|Configura|Convers|Mensagem|Enviar|Carreg|Salvar|Cancelar|Usuário|Senha|Erro|Fechar|Abrir|Pesquis|Buscar|Modelo|Excluir|Adicionar|Remover|Perfil|Tema|Claro|Escuro|Sistema|Sair|Novo|Voltar|Ativar|Desativar|Favorit|Apagar|Sincroniz|Preferên|Selecion|Instalar|Busca|Raciocín|Pensando|Concluíd|Artefato|Provedor|Gerenciar|Administrad|Geral|Ferrament|Privacid|Permiss|Cobrança|Calibra|Ranking|Cache|Fusion|Melhor|Visão|Família|Háptico|Aparên|Fonte|Dispositivo|Ontem|Hoje|Mais antigos|Últimos|Nenhuma|Nenhum|Procurar|Entrar|Cadastre|placeholder|title=|aria-label/

const found = new Map()
const stringRe = /(['"`])((?:\\.|(?!\1)[^\\])*)\1/g

for (const f of files) {
  const t = fs.readFileSync(f, 'utf8')
  let m
  while ((m = stringRe.exec(t))) {
    let s = m[2]
    if (s.includes('${')) continue
    s = s.replace(/\\n/g, '\n').replace(/\\'/g, "'").replace(/\\"/g, '"')
    if (s.length < 2 || s.length > 220) continue
    if (!ptHints.test(s) && !/^[A-ZÁÉÍÓÚÃÕÂÊÔ][a-záéíóúãõâêôç ]{3,}/.test(s)) continue
    // skip imports/paths/css-ish
    if (s.includes('/') && s.length < 40) continue
    if (s.startsWith('var(') || s.startsWith('nexuslocal') || s.startsWith('http')) continue
    if (!found.has(s)) found.set(s, path.relative(src, f).replace(/\\/g, '/'))
  }
}

const out = [...found.entries()].sort((a, b) => a[1].localeCompare(b[1]) || a[0].localeCompare(b[0]))
console.log('COUNT', out.length)
for (const [s, f] of out) {
  console.log(JSON.stringify(s) + '\t' + f)
}
