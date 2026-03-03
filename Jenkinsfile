pipeline {
    agent any

    environment {
        GCP_PROJECT    = credentials('gcp-project-id')
        GCP_REGION     = 'us-central1'
        REGISTRY       = "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/hemisphere-repo"
        PYTHON_VERSION = '3.11'
    }

    stages {
        stage('Setup') {
            steps {
                sh '''
                    python${PYTHON_VERSION} -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -e ".[dev]"
                '''
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    . .venv/bin/activate
                    ruff check .
                    ruff format --check .
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    . .venv/bin/activate
                    python -m pytest tests/ terraform/tests/ -v \
                        --tb=short -m "not integration" \
                        --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Terraform Validate') {
            steps {
                dir('terraform') {
                    sh '''
                        terraform init -backend=false
                        terraform validate
                    '''
                }
            }
        }

        stage('Cloud Build') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    gcloud builds submit . \
                        --project="${GCP_PROJECT}" \
                        --config=cloudbuild.yaml \
                        --substitutions="_REGISTRY=${REGISTRY}" \
                        --quiet
                '''
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh 'scripts/deploy.sh'
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
