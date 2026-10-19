# Privacidade e LGPD

> **Rascunho técnico.** Descreve o que o produto faz hoje com dados pessoais, para embasar a Política de Privacidade e os Termos de Uso. **Precisa de revisão jurídica** antes do lançamento comercial (controlador, encarregado, base legal, transferência internacional).

## Princípios
- **Mínimo necessário:** buscar, ler e navegar pelo feed **não exigem conta** nem identificação.
- **Controle da pessoa:** exportar tudo e excluir a conta estão na própria interface.
- **Sem rastreamento de terceiros:** o produto não carrega scripts, fontes ou imagens de terceiros no navegador (CSP `default-src 'self'`) e não usa análise de audiência nem publicidade.
- **IA com dados públicos:** o que vai ao modelo de linguagem é o título e o resumo do artigo, não dados da conta.

## Dados tratados
| Dado | Origem | Finalidade | Onde fica | Retenção |
|---|---|---|---|---|
| E-mail | Cadastro | Identificar a conta | `users` | Até a exclusão da conta |
| Hash e sal da senha | Cadastro | Autenticação | `users` | Até a exclusão (a senha em si nunca é guardada) |
| Biblioteca, etiquetas, listas | Uso | Função do produto | `library_items`, `reading_lists`… | Até a pessoa remover ou excluir a conta |
| Análises salvas | Uso | Função do produto | `saved_analyses` | Idem |
| Relatórios (itens, notas, versões, histórico) | Uso | Função do produto | `reports*` | Idem (versões: 50; histórico: 200) |
| Interesses e avisos | Uso | Alertas e sininho | `interest_*`, `alerts`, `notifications` | Idem (avisos: até 200) |
| Perfil de uso | Escolha da pessoa | Ajustar o que é destacado | `user_profiles` | Idem |
| Cookie de sessão | Login | Manter a pessoa logada | Navegador | 7 dias |
| Endereço IP | Conexão | Limitar abuso (limitadores em memória) | **Memória do processo**, não gravado em banco | Até o reinício do serviço |
| Contagem de tokens de IA | Uso do Laboratório | Cota e custo | Memória e linha de log (sem conteúdo nem identificação) | Logs do provedor |
| Texto de buscas | Uso | Resultado da busca | Cache em memória (10 min); parâmetros ficam na URL do navegador | Curta |

Não são tratados dados sensíveis (art. 5º, II) como categoria buscada pelo produto. **Atenção:** a biblioteca e os interesses de uma pessoa podem revelar assuntos de saúde de interesse dela (por exemplo, temas de doenças); trate-os com o mesmo cuidado de dados sensíveis e nunca os use para outra finalidade.

## Direitos dos titulares e como são atendidos
| Direito | Como atender hoje |
|---|---|
| Confirmação e acesso | *Perfil → Conta e dados → Baixar meus dados* (`meus-dados.json`) |
| Portabilidade | O mesmo arquivo (JSON); a biblioteca também exporta em BibTeX, RIS e outros |
| Correção | A pessoa edita biblioteca, listas, relatórios, interesses e perfil; troca a senha; o e-mail não é editável (pendência) |
| Eliminação | *Perfil → Conta e dados → Excluir conta*: apaga conta, biblioteca, listas, análises, relatórios, interesses, avisos e perfil. Irreversível |
| Revogação / oposição | Excluir a conta; desligar tipos de aviso em *Perfil → Notificações* |
| Informação sobre compartilhamento | Ver "Operadores e transferências" abaixo |

### Atendimento de solicitações
Para quem não consegue entrar (senha perdida): verificar a identidade por canal acordado, executar a exportação ou a exclusão diretamente no banco (funções `delete_user_data` de cada armazém e remoção em `users`) e registrar o atendimento (data, solicitação, ação). Prazo-alvo de resposta: 15 dias. **Definir canal oficial de contato do encarregado.**

## Bases legais (proposta)
- Cadastro e funções da conta: **execução de contrato** (art. 7º, V) com os Termos de Uso.
- Avisos no site (sininho): parte da função contratada; avisos por e-mail/push futuros dependem de **consentimento** específico.
- Registros de segurança e limite de abuso: **legítimo interesse** (art. 7º, IX).

## Operadores e transferências internacionais
| Operador | O que recebe | Observação |
|---|---|---|
| Render (hospedagem) | Todo o tráfego e os dados do serviço | Verificar região e cláusulas contratuais (infraestrutura nos EUA/Europa) |
| Provedor do PostgreSQL | Dados da conta | Idem; confirmar região, criptografia e backups |
| Groq | Título e resumo do artigo enviados ao Laboratório de IA | Sem dados pessoais; verificar política de retenção e de treinamento do plano contratado |
| GitHub | Código; *Actions* chama a rotina agendada com um token | Sem dados pessoais |
| Fontes de artigos e feeds | Termos de busca (parâmetros enviados pelo servidor, sem identificar a pessoa) | O servidor consulta em nome da pessoa; **a pessoa não é identificada** |

Pendência: registrar contratos/DPAs com os operadores e atualizar este quadro com as regiões reais.

## Segurança dos dados
Ver [Segurança](../arquitetura/seguranca.md): senhas com PBKDF2 (600 mil iterações), sessão assinada com `HttpOnly`/`Secure`, TLS no provedor, CSP restritiva, limites de acesso por dono em todas as consultas e minimização de logs (sem conteúdo nem identificação).

## Incidentes
1. Conter (revogar segredos, trocar `SESSION_SECRET` para encerrar sessões, desativar a rota afetada).
2. Avaliar o que foi exposto e quem foi afetado.
3. Comunicar a ANPD e os titulares quando houver risco ou dano relevante, em prazo razoável (a ANPD indica 3 dias úteis como referência para comunicação de incidentes de segurança).
4. Registrar causa, correção e aprendizado.

## Pendências
1. Política de Privacidade e Termos de Uso redigidos por advogado.
2. Indicação do encarregado (DPO) e canal de contato.
3. Aviso de privacidade e consentimento visíveis no cadastro.
4. E-mail transacional (confirmação de endereço e recuperação de senha) com base legal e opt-out.
5. Registro das operações de tratamento (ROPA) e RIPD se o escopo crescer.
6. Política de retenção para contas inativas.
