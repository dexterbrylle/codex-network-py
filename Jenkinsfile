pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                git credentialsId: 'Github-Token', url: 'https://github.com/dexterbrylle/codex-network-py.git', branch: 'main' // Or your main branch name
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    dockerImageName = "dexterbrylle/codex-network-py"
                    dockerfilePath = '.'

                    docker.build(dockerImageName, dockerfilePath)
                }
            }
        }

        stage('Test') {
            steps {
                script {
                    sh 'pip install -r requirements.txt'
                    sh 'pip install pytest'

                    //sh 'pytest'
                    sh 'flake8'
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    dockerImageName = "dexterbrylle/codex-network-py"
                    docker.withRegistry('https://index.docker.io/v1/', 'dockerhub-credentials') { // Configure Docker Hub credentials in Jenkins
                        docker.image(dockerImageName).push()
                    }
                }
            }
        }
    }

}