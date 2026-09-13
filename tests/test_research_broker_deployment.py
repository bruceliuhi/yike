from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_broker_deployment_is_private_persistent_and_separate():
    path = ROOT / 'deploy/compose.research-broker.yml'
    assert path.exists(), 'independent broker deployment missing'
    config = path.read_text()
    assert 'pilot:' not in config
    assert 'ports:' not in config
    assert 'env_file:' not in config
    assert 'network_mode: none' in config
    assert 'restart: unless-stopped' in config
    assert 'user: "10001:10001"' in config
    assert 'read_only: true' in config
    assert 'no-new-privileges:true' in config
    assert 'pilot.research_broker_service' in config
    assert 'YIKE_BROKER_IMAGE:?' in config
    assert 'YIKE_RESEARCH_IMAGE_ID:?' in config
    assert 'YIKE_DOCKER_GID:?' in config
    # Task paths must match the Docker host, not a differently named volume.
    assert 'source: /var/lib/yike-r/tasks' in config
    assert 'target: /var/lib/yike-r/tasks' in config
    assert config.count('create_host_path: false') == 5
    assert 'source: /var/run/docker.sock' in config


def test_customer_baseline_does_not_gain_docker_control():
    config = (ROOT / 'deploy/compose.pilot.yml').read_text()
    assert 'docker.sock' not in config
    assert 'group_add:' not in config
