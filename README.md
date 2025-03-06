# CodeOwners Rotator

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Version](https://img.shields.io/badge/version-0.1.0--alpha-orange)

**CodeOwners Rotator** é uma ferramenta automatizada para simplificar o gerenciamento de revisores em seus projetos. Ela realiza a rotação automática de CODEOWNERS em múltiplos repositórios e notifica os revisores designados quando novas solicitações de mesclagem são criadas.

## 🚀 Recursos

- ✅ Rotação automática diária de CODEOWNERS
- ✅ Suporte para múltiplos repositórios GitLab
- ✅ Notificações via Slack para revisores designados quando pipelines são executadas
- ✅ Distribuição justa da carga de revisão
- ✅ Fácil de configurar e executar via Docker

## 🔜 Em Desenvolvimento (Coming Soon)

- 🚧 Suporte para GitHub
- 🚧 Suporte para Bitbucket
- 🚧 Notificações via Microsoft Teams
- 🚧 Notificações via Email
- 🚧 Integração com Amazon S3 para armazenamento
- 🚧 Interface web para visualização e gestão
- 🚧 Métricas avançadas de desempenho

## 📋 Pré-requisitos

- Docker e Docker Compose
- Tokens de acesso GitLab (com permissões de API)
- Token de API Slack (para notificações)
- Bucket GCS ou armazenamento local para persistência (opcional)

## 🛠️ Instalação

### Via Docker (Recomendado)

```bash
# Baixar a imagem
docker pull codeowners/rotator:latest

# Preparar arquivo de configuração
cp config.yaml.example config.yaml
# Edite config.yaml com suas configurações

# Executar o container
docker run -v $(pwd)/config.yaml:/app/config.yaml \
  -e GITLAB_TOKEN=seu_token \
  -e SLACK_TOKEN=seu_token_slack \
  codeowners/rotator:latest
```

### Via Docker Compose

```bash
# Clone o repositório
git clone https://github.com/KelvinVenancio/codeowners-rotator.git
cd codeowners-rotator

# Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais

# Inicie com Docker Compose
docker-compose up -d
```

## ⚙️ Configuração

Crie um arquivo `config.yaml` com a seguinte estrutura:

```yaml
# Configuração de plataforma
platform:
  type: gitlab  # ou github, bitbucket
  url: https://gitlab.example.com/
  token: ${GITLAB_TOKEN}  # Use variável de ambiente ou coloque diretamente

# Repositórios para gerenciar
repositories:
  - namespace/repo1
  - namespace/repo2
  - namespace/repo3

# Lista de revisores elegíveis
reviewers:
  - username1
  - username2
  - username3
  - username4

# Configuração de notificação
notification:
  type: slack  # (teams e email - coming soon)
  token: ${SLACK_TOKEN}
  
# Configuração de armazenamento
storage:
  type: gcs  # ou local (s3 - coming soon)
  bucket: my-rotation-bucket
  prefix: codeowners/
```

## 🔄 Uso

### Execução Manual

```bash
# Rotação imediata de CODEOWNERS
docker run codeowners/rotator --rotate-now

# Verificar configuração
docker run codeowners/rotator --check-config

# Testar notificações
docker run codeowners/rotator --test-notification
```

### Uso para Notificações em Pipelines

Para notificar os revisores quando uma MR precisa de aprovação, adicione o seguinte stage à sua pipeline:

```yaml
notify-reviewers:
  stage: notify
  image: codeowners/rotator:latest
  script:
    - /app/notify.sh
  variables:
    SLACK_TOKEN: ${SLACK_TOKEN}
  only:
    - merge_requests
```

Este step lerá o arquivo CODEOWNERS atual e enviará notificações diretamente aos revisores designados via Slack quando a pipeline for executada, sem interferir no processo de rotação diária.

### Configuração via GitLab CI

Exemplo de arquivo `.gitlab-ci.yml` para rotação diária:

```yaml
codeowners-rotation:
  image: codeowners/rotator:latest
  script:
    - /app/run.sh --rotate
  variables:
    GITLAB_TOKEN: ${CI_TOKEN}
    SLACK_TOKEN: ${SLACK_TOKEN}
  only:
    - schedules
```

## 🧩 Extensões

O sistema é modular e pode ser estendido através de adaptadores para:

- **Plataformas**: GitLab, GitHub, Bitbucket
- **Armazenamento**: GCS, S3, local
- **Notificação**: Slack, Teams, Email

Consulte a [documentação de plugins](docs/plugins.md) para mais informações.

## 📊 Métricas e Monitoramento

O CodeOwners Rotator expõe métricas Prometheus na porta 9090 por padrão, incluindo:
- Tempo de execução de rotação
- Sucesso/falha de atualizações de CODEOWNERS
- Notificações enviadas

## 📚 Documentação

- [Guia de Configuração Avançada](docs/advanced-config.md)
- [Arquitetura](docs/architecture.md)
- [FAQ](docs/faq.md)
- [Solução de Problemas](docs/troubleshooting.md)

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, consulte [CONTRIBUTING.md](CONTRIBUTING.md) para obter detalhes.

## 📄 Licença

Este projeto está licenciado sob a [Apache License 2.0](LICENSE).

## 🙏 Agradecimentos

- Meu time de SRE que inspirou a criação desta ferramenta
- Comunidade open source
