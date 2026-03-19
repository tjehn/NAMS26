# Ansible Vault

Store encrypted secrets here (passwords, keys, tokens).
Never commit plaintext credentials to this directory.

Usage:
  ansible-vault create secrets.yaml
  ansible-vault edit secrets.yaml
  ansible-vault decrypt secrets.yaml   # for local use only — re-encrypt before committing
