export type HowItWorksStep = {
  id: string
  number: number
  title: string
  description: string
  imageSrc: string
  imageAlt: string
}

// Conteúdo específico do Docksmith — cada passo mapeia um momento real do
// fluxo (extrair → indexar → perguntar → aprofundar), não um roteiro
// genérico de marketing. As imagens em imageSrc são screenshots reais do
// produto, capturadas em frontend/public/how-it-works/ (ver Fase 6).
export const HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    id: "entrada",
    number: 1,
    title: "Entrar no Docksmith",
    description:
      "Acesse pelo Hub Syncron — você já entra logado automaticamente, sem precisar fazer login de novo dentro do Docksmith.",
    imageSrc: "/how-it-works/01-entrada.jpg",
    imageAlt: "Tela inicial do Docksmith logo após o acesso, mostrando o formulário de nova extração",
  },
  {
    id: "modelo",
    number: 2,
    title: "Escolher o modelo de IA",
    description:
      "Abra \"Modelo de IA\" e escolha uma das recomendações prontas (custo-benefício, rápida, precisa ou profunda) ou configure manualmente provedor, modelo e sua própria chave de API.",
    imageSrc: "/how-it-works/02-modelo.jpg",
    imageAlt: "Painel de configuração de modelo de IA com os cartões de recomendação",
  },
  {
    id: "extracao",
    number: 3,
    title: "Iniciar uma extração",
    description:
      "Informe a URL de um site técnico, dê um nome à coleção e escolha quanto o Docksmith deve explorar — ele lê e organiza tudo automaticamente.",
    imageSrc: "/how-it-works/03-extracao.jpg",
    imageAlt: "Formulário de nova extração preenchido com uma URL e nome de coleção",
  },
  {
    id: "processamento",
    number: 4,
    title: "Acompanhar o processamento",
    description:
      "O Docksmith organiza tudo automaticamente e deixa pronto para você perguntar — nada fica salvo depois que a sessão termina.",
    imageSrc: "/how-it-works/04-processamento.jpg",
    imageAlt: "Indicador de carregamento durante o processamento da extração",
  },
  {
    id: "resultado",
    number: 5,
    title: "Ver o resultado",
    description:
      "Pergunte em linguagem natural. A resposta vem formatada — conclusão objetiva primeiro, fundamentação em seguida — em vez de um bloco de texto corrido.",
    imageSrc: "/how-it-works/05-resultado.jpg",
    imageAlt: "Resposta do Docksmith renderizada no chat com formatação markdown",
  },
  {
    id: "aprofundamento",
    number: 6,
    title: "Aprofundar a análise",
    description:
      "Abra \"Ver análise completa\" para navegar por Resumo, Insights, Evidências, Dados e Técnico sem perder o fio da resposta original.",
    imageSrc: "/how-it-works/06-aprofundamento.jpg",
    imageAlt: "Painel de análise completa aberto sobre a resposta do chat",
  },
  {
    id: "evidencias",
    number: 7,
    title: "Conferir evidências e fontes",
    description:
      "Cada resposta mostra exatamente de onde veio a informação — nada é inventado além do que está no material original.",
    imageSrc: "/how-it-works/07-evidencias.jpg",
    imageAlt: "Aba de evidências mostrando trechos-fonte expansíveis",
  },
  {
    id: "tecnico",
    number: 8,
    title: "Ver detalhes técnicos",
    description:
      "Provedor, modelo e profundidade usados em cada resposta ficam sempre visíveis, para você saber exatamente o que gerou aquele resultado.",
    imageSrc: "/how-it-works/08-tecnico.jpg",
    imageAlt: "Aba técnica mostrando o provedor e modelo usados na resposta",
  },
  {
    id: "mobile",
    number: 9,
    title: "Usar no celular",
    description:
      "A experiência completa — extração, chat e análise — funciona igual em telas pequenas, sem recursos escondidos.",
    imageSrc: "/how-it-works/09-mobile.jpg",
    imageAlt: "Docksmith aberto em um smartphone, mostrando o chat",
  },
]
