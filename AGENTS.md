# Instrucoes do projeto

Monitor em src/pc_monitor.py: sensores do PC → renderizacao Pillow → HTTP SmallTV. Configuracao local e estado de cache nao devem ser publicados. Nao executar descoberta de rede nem exclusao no dispositivo durante testes.

Ler README e docs antes de alterar. Preservar arquitetura, dados brutos e
autoria/licencas dos materiais externos. Nao inventar hardware, medidas ou
resultados. Marcar UNKNOWN/NOT_MEASURED e separar SIMULATED de REAL.
Fazer mudancas pequenas, com regressao para defeitos corrigidos.

Validacao: `python -m unittest discover -s tests -v`; HTTP e persistencia substituidos por mocks.

Definition of Done: verificacoes pertinentes, documentacao das alteracoes,
comandos reproduziveis e limites de validacao. Inspecao estatica nao comprova
funcionamento fisico. Ver docs/engineering-status.md para prioridades e estudo.
