pipeline {
    agent any

    environment {
        GCP_PROJECT    = credentials('gcp-project-id')
        GCP_REGION     = 'us-central1'
        REGISTRY       = "gcr.io/${GCP_PROJECT}"
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

        stage('Build Images') {
            parallel {
                stage('RH Planner') {
                    steps {
                        sh "docker build -t ${REGISTRY}/rh-planner:${BUILD_NUMBER} docker/rh-planner/"
                    }
                }
                stage('LH Executor') {
                    steps {
                        sh "docker build -t ${REGISTRY}/lh-executor:${BUILD_NUMBER} docker/lh-executor/"
                    }
                }
                stage('Operator') {
                    steps {
                        sh "docker build -t ${REGISTRY}/operator:${BUILD_NUMBER} operator/"
                    }
                }
            }
        }

        stage('Push Images') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    gcloud auth configure-docker --quiet
                    docker push ${REGISTRY}/rh-planner:${BUILD_NUMBER}
                    docker push ${REGISTRY}/lh-executor:${BUILD_NUMBER}
                    docker push ${REGISTRY}/operator:${BUILD_NUMBER}
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
