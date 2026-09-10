# Configurar Cloudflare R2 (armazenamento durável, opcional)

> **A Cloudflare exige cartão de crédito cadastrado pra ativar o R2, mesmo no nível gratuito** (ver seção "O que você precisa saber antes de começar" abaixo). Se isso for um problema, [`CONFIGURAR_ARMAZENAMENTO.md`](./CONFIGURAR_ARMAZENAMENTO.md) documenta o Backblaze B2 como alternativa — mesmo nível gratuito permanente, mesma API S3-compatível, **sem exigir cartão** — usando exatamente o mesmo código deste projeto, sem nenhuma mudança de lógica. Este documento (R2) continua 100% válido pra quem já tem cartão cadastrado ou prefere ficar no ecossistema Cloudflare.

**Resolve o achado real desta sessão: "documentos ainda somem a cada reinício do servidor".** Hoje, tudo que o Docksmith sabe sobre uma sessão (os documentos que você enviou, o texto já extraído, o índice de busca já montado) vive só na memória do processo — sem nenhum banco de dados, sem disco. Se o servidor reiniciar no meio da sua sessão (um deploy, uma queda, uma instabilidade qualquer), tudo isso some e você precisa reenviar os arquivos.

Esta configuração resolve isso guardando uma cópia de segurança de cada arquivo enviado num serviço de armazenamento externo (Cloudflare R2) — se o servidor reiniciar, o Docksmith consegue trazer seus documentos de volta automaticamente, sem você precisar fazer nada.

**É 100% opcional.** Sem configurar nada disso, o Docksmith continua funcionando exatamente como sempre funcionou — só sem essa proteção extra. Nenhuma das 4 variáveis abaixo é obrigatória, nem em produção.

---

## O que você precisa saber antes de começar

- **É gratuito para o uso real desta ferramenta.** O plano gratuito do Cloudflare R2 dá 10GB de armazenamento, 1 milhão de operações de escrita e 10 milhões de operações de leitura **por mês**, de graça, **para sempre** (diferente da AWS, cujo plano gratuito expira depois de 12 meses). E o R2 não cobra nada para você **baixar** os arquivos de volta (isso é raro — a maioria dos serviços parecidos cobra por isso).
- **A Cloudflare pede um cartão de crédito para ativar o R2**, mesmo que você nunca saia do plano gratuito. Isso não significa que você vai ser cobrado — é só uma exigência da Cloudflare para ligar o produto. Se isso te incomoda, você pode simplesmente não configurar o R2 (a ferramenta funciona normalmente sem ele) ou acompanhar o uso pelo painel da Cloudflare de vez em quando para ter certeza de que está sempre dentro do limite gratuito.
- **O uso desta ferramenta fica bem dentro do limite gratuito por design**, não por sorte: cada arquivo enviado é apagado do R2 automaticamente quando a sua sessão expira (1 hora de inatividade, por padrão) — não é uma biblioteca permanente de documentos, é só uma cópia de segurança temporária, do tamanho da sua sessão atual.
- **Tamanho máximo de um arquivo enviado: 300MB** (configurável, ver abaixo — nunca passa disso, não importa o que for configurado). Além disso, existem 2 cotas de segurança extras (por usuário e do bucket inteiro) explicadas na seção própria mais abaixo — pensadas especificamente para nunca deixar o uso real chegar perto dos 10GB gratuitos, mesmo em cenários de muitos uploads/muitos usuários ao mesmo tempo.

---

## Passo a passo

### 1. Criar uma conta na Cloudflare (se você ainda não tiver uma)

Acesse [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up) e crie uma conta gratuita. Não precisa ter nenhum domínio próprio nem site cadastrado — só a conta.

### 2. Ativar o R2

1. No painel da Cloudflare, procure "R2 Object Storage" no menu lateral.
2. Clique em "Ativar" / "Get started" — é aqui que ela vai pedir o cartão de crédito (ver o aviso acima).
3. Depois de ativado, clique em "Criar bucket" (Create bucket).
4. Dê um nome ao bucket, por exemplo `docksmith-documentos`. Localização: pode deixar automática.

### 3. Criar as credenciais de acesso (API Token)

1. Ainda na seção R2, procure "Gerenciar tokens de API R2" (Manage R2 API Tokens).
2. Clique em "Criar API Token" (Create API Token).
3. Permissão: escolha **"Admin Read & Write"** ou, se quiser ser mais restritivo, "Object Read & Write" com escopo limitado ao bucket que você criou.
4. Depois de criar, a Cloudflare mostra 3 informações **uma única vez** — copie e guarde num lugar seguro (ex.: um gerenciador de senhas) antes de sair da tela:
   - **Access Key ID**
   - **Secret Access Key**
   - **Endpoint** (algo como `https://<um-código>.r2.cloudflarestorage.com`) — o `<um-código>` no meio dessa URL é o seu **Account ID**.

Se você perder o Secret Access Key, não tem problema — é só apagar esse token e criar um novo, gratuitamente, quantas vezes precisar.

### 4. Configurar as 4 variáveis de ambiente

No ambiente onde o Docksmith roda (seu `.env` local para testar, ou as variáveis de ambiente do host de produção — Railway, Render, etc.), defina:

```bash
R2_ACCOUNT_ID=o-codigo-que-aparece-no-endpoint
R2_ACCESS_KEY_ID=o-access-key-id-que-voce-copiou
R2_SECRET_ACCESS_KEY=o-secret-access-key-que-voce-copiou
R2_BUCKET_NAME=docksmith-documentos
```

Pronto. Na próxima vez que o Docksmith iniciar, ele detecta essas 4 variáveis automaticamente e passa a guardar uma cópia de segurança de cada arquivo enviado. Nenhuma outra configuração é necessária.

### 5. Confirmar que está funcionando (opcional)

Envie um documento normalmente pelo Docksmith. Depois, no painel da Cloudflare, abra o seu bucket — você deve ver um objeto novo lá dentro (o nome do objeto é um código opaco, não o nome do seu arquivo — isso é proposital, ver "Como isso funciona" abaixo).

---

## O tamanho máximo de arquivo (300MB) e por quê

Por padrão, o Docksmith aceita arquivos de até 20MB (o suficiente para a maioria dos PDFs/documentos do dia a dia). Se você quiser aumentar esse limite (até o teto absoluto de 300MB, que nunca pode ser ultrapassado mesmo por engano de configuração), defina:

```bash
DOCSMITH_MAX_FILE_SIZE_MB=300
```

**Por que 300MB, e não mais** (esse número foi pensado de propósito, não é um valor arbitrário): o Docksmith já limita todo documento a 300 páginas (`DOCSMITH_MAX_PAGES`). Um livro real de até 300 páginas, mesmo bem ilustrado, praticamente nunca chega perto de 300MB — um arquivo muito maior que isso quase sempre é um PDF escaneado em resolução muito alta, o que o Docksmith não processa bem de qualquer forma (ele precisa de texto real que dê para selecionar/copiar dentro do PDF, não de reconhecimento de imagem/OCR — ver a seção sobre isso na documentação principal). Ou seja: 300MB já cobre com folga qualquer livro/relatório/manual real que o Docksmith consegue efetivamente aproveitar.

**Isso funciona independente de você ter configurado o R2 ou não** — mas vale saber: mesmo com o R2 configurado, o servidor ainda precisa ler o arquivo inteiro na memória por um instante para extrair o texto dele (não tem como evitar isso completamente — é assim que qualquer leitor de PDF/DOCX funciona). O R2 resolve o problema de **guardar** o arquivo depois — não o de processá-lo. Por isso, se você for aumentar bastante esse limite, é bom garantir que o servidor onde o Docksmith roda tenha memória (RAM) suficiente disponível para arquivos desse tamanho.

---

## As 2 cotas de segurança do R2 (por quê e como funcionam)

O limite de 300MB por arquivo protege contra **um** upload muito grande — mas sozinho, não impede que a mesma pessoa envie vários arquivos (cada um dentro do limite) e acabe acumulando muito mais que isso no R2, nem impede que **muitos usuários diferentes**, todos ao mesmo tempo, somem mais do que o plano gratuito aguenta. Por isso existem mais 2 camadas de proteção, checadas automaticamente antes de cada backup:

1. **Cota por usuário — 1GB por padrão.** Soma de tudo que uma única conta tem guardado no R2 agora (contando todas as sessões ativas dela). Configurável:
   ```bash
   DOCSMITH_R2_MAX_MB_PER_USER=1024
   ```
2. **Cota global do bucket — 6GB por padrão.** Soma de **tudo** que está no bucket, de **todos** os usuários juntos — a rede de segurança final, mesmo que muitas contas diferentes estejam ativas ao mesmo tempo. Deixa 4GB de folga real abaixo do teto gratuito de 10GB. Configurável:
   ```bash
   DOCSMITH_R2_MAX_MB_TOTAL_BUCKET=6144
   ```

**O que acontece quando uma dessas cotas é atingida: nada quebra.** O documento continua sendo enviado, processado e ficando disponível pra conversa normalmente — só a cópia de segurança daquela vez específica não é criada (fica registrado nos logs do servidor, silenciosamente, sem aparecer como erro pra você). Assim que a cota abrir espaço de novo (sessões antigas expirando e sendo limpas automaticamente), os próximos uploads voltam a ganhar backup normalmente.

---

## Como isso funciona por baixo dos panos (se você tiver curiosidade)

- Cada arquivo é guardado sob um "endereço" opaco no R2 (um código aleatório, nunca o nome real do arquivo nem o seu identificador de usuário) — pensado para que, mesmo alguém com acesso ao bucket, não consiga associar um arquivo a uma pessoa só olhando os nomes.
- Quando sua sessão expira (1 hora sem uso, por padrão), a cópia de segurança correspondente é apagada automaticamente — o R2 nunca guarda nada para sempre, só enquanto a sua sessão está "viva".
- Se o servidor reiniciar enquanto sua sessão ainda está ativa, o Docksmith detecta que os seus documentos sumiram da memória e os traz de volta do R2 automaticamente na primeira vez que você tentar usá-los de novo — sem você precisar fazer nada.
- Se você reaproveitar um link/sessão antiga de **outra pessoa** (por engano ou de propósito), o Docksmith nunca vai conseguir restaurar os documentos dela — a verificação de que os documentos pertencem a você é feita de novo a cada tentativa de restauração.

---

## O que ISSO NÃO resolve (registrado com transparência)

- **Não existe ainda uma fila de processamento de verdade.** O upload de um arquivo continua sendo processado (extração de texto, indexação) na hora, dentro da mesma requisição — só a cópia de segurança do arquivo original é que roda depois, sem atrasar sua resposta. Uma fila real (processamento em segundo plano, com retry automático) é uma mudança maior, ainda não construída.
- **A validação do tipo de arquivo continua indireta** (baseada na extensão do nome do arquivo, ex. `.pdf`/`.docx`), sem uma checagem independente do conteúdo real do arquivo.
- **Não há métricas formais de uso** (quanto cada pergunta custa, quanto tempo demora, etc.) — nem do R2, nem do resto do Docksmith.

Nenhum desses 3 pontos depende do R2 para ser resolvido — são melhorias separadas, registradas aqui só para você ter o quadro completo.
