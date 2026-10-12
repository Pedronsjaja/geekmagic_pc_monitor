# Cache HTTP e validacao — 2026-10-12

Corrigido: falhas HTTP/de conexao em exclusoes deixavam o cache local sem
registro do arquivo, com mensagem de sucesso indevida. Agora somente resposta
HTTP aceita remove a entrada; falhas preservam a tentativa futura. Nomes
fora do prefixo pcmon_ ou contendo separadores de caminho sao recusados.
Resposta HTTP 2xx nao comprova exclusao fisica em todo firmware SmallTV.

TESTADO AUTOMATICAMENTE: 5 testes offline com unittest (HTTP 503, timeout,
falha persistente, limite do cache e nomes externos). NAO TESTADO NO DISPOSITIVO.

Prioridades: ALTO verificar resposta real do firmware e consulta posterior da
lista; MEDIO medir latencia e ocupacao de armazenamento; BAIXO separar a
renderizacao da coleta se novas telas justificarem. Firmware/modelo usado:
UNKNOWN; latencia de upload: NOT_MEASURED. Nao preencher ausencias com zero.

Para entender esta implementacao: siga delete_image → remove_cached_frame →
cleanup/trim_cache. Estude consistencia entre estado remoto e local e
idempotencia. Desafio: simule uma exclusao aceita seguida de timeout e
verifique que apenas a segunda entrada permanece.

Referencia: [Requests: status HTTP](https://requests.readthedocs.io/en/latest/user/quickstart/#response-status-codes).
O metodo raise_for_status identifica erro HTTP; nao verifica a semantica
especifica do firmware. Nenhuma medicao fisica e inferida dessa documentacao.
