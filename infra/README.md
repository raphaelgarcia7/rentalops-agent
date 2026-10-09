# Infraestrutura

Preparação portátil aprovada em #4: Docker Compose em um host Linux dedicado,
PostgreSQL e arquivos privados em volumes separados, frontend estático/nginx.
[Runbook e comandos de backup/verify/restore](operations/README.md).

Fornecedor, domínio/TLS, acesso real, monitor externo, destino de backup fora do host
e política de eliminação são gates anteriores à exposição. A preparação local não
contrata, provisiona nem implanta serviços e não certifica objetivos de produção.
