# PharmaAssist - AI-Powered Virtual Drug & Treatment Assistant

## 🏥 Overview

PharmaAssist is a production-grade, cloud-native microservice that leverages AWS AI/ML services to provide intelligent drug information, treatment recommendations, and drug-drug interaction checking. Built with a serverless-first architecture on AWS, it delivers enterprise-grade reliability, scalability, and security for healthcare applications.

### Key Features

- 🤖 **AI-Powered Drug Assistant** - Natural language understanding using Amazon Bedrock & Comprehend Medical
- 💊 **Drug Information Retrieval** - Comprehensive drug database with RAG-enhanced responses
- ⚠️ **Drug Interaction Checker** - Real-time drug-drug interaction analysis
- 📋 **Treatment Protocol Recommendations** - Evidence-based treatment suggestions
- 🔒 **HIPAA-Ready Architecture** - End-to-end encryption, audit logging, PHI protection
- 🌐 **Multi-Model Database** - PostgreSQL (structured data), MongoDB/DocumentDB (unstructured), ElastiCache (caching)
- 📊 **Full Observability** - CloudWatch metrics, X-Ray tracing, structured logging
- 🚀 **Event-Driven Architecture** - SQS/SNS for async processing, EventBridge for workflow orchestration

## 🏗️ Architecture

```

```

## 🚀 Quick Start

### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker & Docker Compose
- Python 3.11+
- Poetry (dependency management)
- Terraform 1.5+

### Local Development

```bash
# Clone repository
git clone https://github.com/your-org/pharma-assistant.git
cd pharma-assistant

# Install dependencies
poetry install --with dev

# Setup pre-commit hooks
poetry run pre-commit install

# Start local infrastructure
docker-compose up -d postgres mongodb redis opensearch localstack

# Run migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

AWS Deployment

```bash
# Initialize Terraform
cd infrastructure/terraform/environments/dev
terraform init
terraform plan
terraform apply

# Build and push Docker image
make build-prod
make push-prod

# Deploy to ECS
make deploy-prod
```

📚 API Documentation

Once running, access interactive API docs:

· Swagger UI: http://localhost:8000/docs
· ReDoc: http://localhost:8000/redoc

Key Endpoints

```python
# Assistant Query
POST /api/v1/assistant/query
{
    "query": "What are the side effects of metformin?",
    "context": {"patient_age": 65, "conditions": ["type 2 diabetes"]}
}

# Drug Search
GET /api/v1/drugs/search?name=metformin&limit=10

# Interaction Check
POST /api/v1/interactions/check
{
    "drugs": ["warfarin", "aspirin", "ibuprofen"]
}

# Treatment Recommendations
POST /api/v1/treatments/recommend
{
    "diagnosis": "hypertension",
    "patient_factors": {"age": 55, "pregnancy": false}
}
```

🔐 Security

· Data Encryption: AES-256-GCM with AWS KMS managed keys
· Transit Security: TLS 1.3 for all communications
· Authentication: AWS Cognito with JWT validation
· Authorization: IAM-based fine-grained access control
· Audit Logging: Immutable CloudWatch Logs with integrity validation
· Secrets Management: AWS Secrets Manager with automatic rotation
· Vulnerability Scanning: Trivy, SonarQube, Dependabot

📊 Monitoring & Observability

· Metrics: Custom CloudWatch metrics with 1-minute granularity
· Tracing: AWS X-Ray distributed tracing with subsegment analysis
· Logging: Structured JSON logging with correlation IDs
· Alerting: CloudWatch Alarms → SNS → PagerDuty/Slack
· Dashboards: CloudWatch Dashboards for business & technical metrics

🧪 Testing

```bash
# Unit tests
poetry run pytest tests/unit -v --cov=src --cov-report=term-missing

# Integration tests (requires Docker)
poetry run pytest tests/integration -v

# End-to-end tests
poetry run pytest tests/e2e -v

# Security scanning
make security-scan
```

📈 Performance Characteristics

· API Latency: p95 < 200ms (cached), p95 < 1s (uncached)
· Throughput: 500+ req/sec per ECS task
· Availability: 99.95% SLA (multi-AZ deployment)
· Scalability: Auto-scaling based on CPU/Memory/Request count

🤝 Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

📄 License

This project is licensed under the MIT License - see LICENSE for details.

🏥 Healthcare Compliance

This service is designed to support HIPAA compliance when properly configured:

· PHI encryption at rest and in transit
· Comprehensive audit trails
· Access controls and authentication
· BAA-eligible AWS services

Important: You must conduct your own compliance assessment and sign BAAs with AWS.

🔗 Related Resources

· Architecture Decision Records
· API Documentation
· Deployment Guide
· Security Whitepaper

```
