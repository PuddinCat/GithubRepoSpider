. .secrets
. /tmp/venv-githubrepospider/bin/activate.fish
python main.py && curl --retry 5 'https://monitor.laserbreakout.eu.org/api/push/T1MqWQpPRP?status=up&msg=OK&ping='
