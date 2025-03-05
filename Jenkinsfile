pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                git url: 'https://github.com/dexterbrylle/codex-network-py.git', branch: 'main'
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