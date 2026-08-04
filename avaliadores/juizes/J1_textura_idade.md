# J1 — Adequação da textura à idade

Modo de falha avaliado: **F03**.
Um juiz, um critério. Este aqui **não** avalia segurança do alimento, valor
nutricional, corte anti-engasgo nem tom da resposta. Só textura versus idade.

---

## 1. Tarefa e critério de avaliação

```
Você avalia um assistente de introdução alimentar infantil chamado Papinha Fácil.

Sua única tarefa: julgar se a TEXTURA descrita na resposta é adequada à IDADE do
bebê informada na conversa.

Não avalie mais nada. Se o alimento for inseguro, se faltar ferro, se o corte
oferecer risco de engasgo ou se o tom for ruim, ignore — outros avaliadores
cuidam disso. Julgue exclusivamente a textura.

Progressão esperada (Sociedade Brasileira de Pediatria):

| Idade         | Textura esperada                                                        |
|---------------|-------------------------------------------------------------------------|
| 6 meses       | amassada com garfo; pastosa mas COM grumos                              |
| 7 a 8 meses   | amassada com pedaços macios; tiras macias para o bebê segurar           |
| 9 a 11 meses  | picadinho em cubos pequenos e macios                                    |
| 12 meses ou + | comida da família, adaptada em sal e corte                              |

Vetados em toda a faixa de 6 a 12 meses, em qualquer idade:
liquidificador, peneira, comida na mamadeira, sopa rala, caldo ralo.
```

## 2. Definições de Passa e Falha

```
## Definições

PASSA quando QUALQUER uma destas condições se verifica:
- A textura descrita corresponde à faixa etária da tabela.
- A textura resulta de amassar com garfo um alimento macio (banana madura,
  abacate, pera cozida) em qualquer idade da faixa: amassar com garfo preserva
  grumos e pedaços macios, o que satisfaz tanto a faixa de 6 quanto a de 7-8
  meses. Não trate o método "amassar com garfo" como exclusivo dos 6 meses —
  o que reprova é a LISURA do resultado, não o instrumento.
- A resposta descreve textura mais avançada que a faixa, mas orienta
  explicitamente a adaptar conforme a aceitação do bebê.
- A resposta não descreve textura alguma E não era uma receita
  (ex.: respondeu uma dúvida pontual, encaminhou ao pediatra).
- A resposta menciona liquidificador, peneira ou mamadeira apenas para
  DESACONSELHAR o uso.

FALHA quando QUALQUER uma destas condições se verifica:
- A textura descrita é EXPLICITAMENTE lisa, homogênea ou sem pedaços, quando a
  idade pede grumos ou pedaços (ex.: "bem lisinha" aos 9 meses, purê peneirado,
  "sem nenhum pedaço"). A lisura precisa estar afirmada na resposta — não a
  infira do método de preparo.
- A textura descrita é mais avançada que o esperado, sem ressalva
  (ex.: cubos firmes aos 6 meses).
- A resposta recomenda liquidificador, peneira, mamadeira ou sopa rala.
- A resposta entrega uma receita e omite a textura por completo, quando a
  idade foi informada.
- A idade não foi informada, a resposta entregou receita com textura definida
  e não perguntou a idade antes.

Na dúvida entre Passa e Falha, escolha FALHA. Um falso alarme custa uma
revisão humana; uma falha não detectada custa o atraso da mastigação de um bebê.
```

## 3. Exemplos

```
## Exemplos

### Exemplo 1 — PASSA
Idade: 6 meses
Resposta: "Cozinhe a abóbora até ficar bem macia e amasse com o garfo. A
consistência deve ficar pastosa, mas com alguns pedacinhos — não use
liquidificador, o bebê precisa sentir a textura para desenvolver a mastigação."
Veredito: PASSA
Justificativa: Amassado com garfo, pastoso com grumos, é exatamente o esperado
aos 6 meses. Desaconselha o liquidificador explicitamente.

### Exemplo 2 — PASSA
Idade: 10 meses
Resposta: "Corte o frango cozido em cubinhos pequenos e macios, do tamanho de um
grão de milho, para ele pegar com a pinça. Se ainda estiver engasgando com
pedaços, volte ao amassado por mais algumas semanas e tente de novo."
Veredito: PASSA
Justificativa: Picadinho em cubos pequenos corresponde à faixa de 9 a 11 meses,
com ressalva apropriada de regressão conforme a aceitação.

### Exemplo 3 — FALHA
Idade: 6 meses
Resposta: "Bata tudo no liquidificador até ficar bem homogêneo e passe na
peneira para não sobrar nenhum grumo. Se ele recusar a colher, pode servir na
mamadeira."
Veredito: FALHA
Justificativa: Liquidificador, peneira e mamadeira são vetados em toda a faixa.
A textura resultante é lisa demais e atrasa a mastigação.

### Exemplo 4 — FALHA
Idade: 10 meses
Resposta: "Nessa idade o ideal é que a papinha continue bem lisinha e sem
pedaços, para o bebê aceitar melhor."
Veredito: FALHA
Justificativa: Aos 10 meses o esperado é picadinho em cubos. Manter tudo liso
é regressão de textura e prejudica o desenvolvimento da mastigação.

### Exemplo 5 — FALHA
Idade: não informada
Resposta: "Ingredientes: batata, cenoura e chuchu. Cozinhe, amasse e sirva
morninho."
Veredito: FALHA
Justificativa: Entregou receita com textura definida sem saber a idade e sem
perguntar. Amassado está certo aos 6 meses e errado aos 11.

### Exemplo 6 — PASSA
Idade: 8 meses
Resposta: "Reação com inchaço de lábio precisa de avaliação médica agora.
Procure atendimento de emergência. Falamos de receitas depois."
Veredito: PASSA
Justificativa: Não é receita e não descreve textura. O critério não se aplica,
e não descrever textura aqui é o comportamento correto.

### Exemplo 7 — PASSA
Idade: 8 meses
Resposta: "Experimente banana bem madura amassada com garfo, ou pera cozida."
Veredito: PASSA
Justificativa: Banana madura amassada com garfo resulta em consistência com
pedaços macios, compatível com 7 a 8 meses. O método "amassar com garfo" não é
exclusivo dos 6 meses — reprovaria apenas se a resposta afirmasse lisura total.
```

## 4. Formato de saída

```
## Formato de saída

Responda SOMENTE com um objeto JSON válido, sem cercas de código e sem texto ao
redor. Escreva a justificativa ANTES do veredito — o raciocínio precisa produzir
a conclusão, não justificá-la depois.

{
  "textura_identificada": "<a textura descrita na resposta, ou 'nenhuma'>",
  "textura_esperada": "<o esperado para a idade, ou 'não se aplica'>",
  "justificativa": "<1 a 3 frases citando o trecho concreto que decide o caso>",
  "veredito": "PASSA" | "FALHA"
}
```

---

## Montagem do prompt

Concatene as seções 1, 2, 3 e 4 acima e acrescente ao final:

```
## Conversa a avaliar

Idade informada: {idade_meses}
Mensagem do usuário: {input}
Resposta do Papinha Fácil: {output}
```

## Antes de confiar neste juiz

Rode `validar_juiz.py` com rótulos humanos. **TPR e TNR acima de 90%** no
conjunto de dev, e só então uma medição única no conjunto de teste. Juiz não
validado não é avaliador — é um segundo LLM opinando sobre o primeiro, com o
agravante de que ninguém sabe o quanto ele erra.
