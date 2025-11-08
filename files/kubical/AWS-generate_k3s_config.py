#!/var/lib/kubical/venv/bin/python3
"""
Generate K3s configuration with AWS metadata.
Outputs YAML to stdout for redirection to /etc/rancher/k3s/config.yaml
"""

import sys
import platform
from ec2_metadata import ec2_metadata
import boto3
import yaml


def get_arch():
    """Get normalized architecture name."""
    machine = platform.machine()
    arch_map = {
        'x86_64': 'amd64',
        'aarch64': 'arm64',
        'armv7l': 'arm',
    }
    return arch_map.get(machine, machine)


def parse_instance_type(instance_type):
    """Parse instance type into family and size."""
    parts = instance_type.split('.')
    if len(parts) == 2:
        return parts[0], parts[1]
    return instance_type, 'unknown'


def get_capacity_type():
    """Determine if instance is spot or on-demand."""
    try:
        # This will return 'spot' for spot instances, or raise an exception for on-demand
        lifecycle = ec2_metadata.instance_life_cycle
        return 'spot' if lifecycle == 'spot' else 'on-demand'
    except:
        return 'on-demand'


def get_instance_tags(instance_id, region):
    """Get tags from the EC2 instance."""
    try:
        ec2 = boto3.client('ec2', region_name=region)
        response = ec2.describe_instances(InstanceIds=[instance_id])
        
        if not response['Reservations']:
            return {}
        
        instance = response['Reservations'][0]['Instances'][0]
        tags = {}
        
        for tag in instance.get('Tags', []):
            tags[tag['Key']] = tag['Value']
        
        return tags
    except Exception as e:
        print(f"Warning: Could not fetch instance tags: {e}", file=sys.stderr)
        return {}


def is_elastic_ip(instance_id, public_ip, region):
    """Check if the public IP is an Elastic IP."""
    if not public_ip:
        return False
    
    try:
        ec2 = boto3.client('ec2', region_name=region)
        
        # Method 1: Check via DescribeAddresses (most reliable)
        try:
            addresses = ec2.describe_addresses(PublicIps=[public_ip])
            if addresses['Addresses']:
                return True
        except ec2.exceptions.ClientError as e:
            # If the address is not found, it's not an EIP
            if 'InvalidAddress.NotFound' in str(e):
                print(f"Debug: IP {public_ip} not found in EIP allocations", file=sys.stderr)
            else:
                print(f"Debug: Error checking addresses: {e}", file=sys.stderr)
        
        # Method 2: Check network interface associations (fallback)
        response = ec2.describe_instances(InstanceIds=[instance_id])
        
        if not response['Reservations']:
            return False
        
        instance = response['Reservations'][0]['Instances'][0]
        
        # Check network interfaces for association
        for iface in instance.get('NetworkInterfaces', []):
            assoc = iface.get('Association', {})
            if assoc.get('PublicIp') == public_ip:
                has_allocation = 'AllocationId' in assoc
                print(f"Debug: Network interface association: {assoc}", file=sys.stderr)
                print(f"Debug: Has AllocationId: {has_allocation}", file=sys.stderr)
                return has_allocation
        
        return False
    except Exception as e:
        print(f"Warning: Could not determine if IP is elastic: {e}", file=sys.stderr)
        return False


def generate_k3s_config():
    """Generate K3s configuration dictionary."""
    try:
        # Fetch metadata
        instance_id = ec2_metadata.instance_id
        az = ec2_metadata.availability_zone
        region = ec2_metadata.region
        instance_type = ec2_metadata.instance_type
        
        # Public IP may be None for instances without public IPs
        try:
            public_ipv4 = ec2_metadata.public_ipv4
        except:
            public_ipv4 = None
        
        # Derived values
        arch = get_arch()
        instance_family, instance_size = parse_instance_type(instance_type)
        capacity_type = get_capacity_type()
        provider_id = f"aws://{az}/{instance_id}"
        is_eip = is_elastic_ip(instance_id, public_ipv4, region) if public_ipv4 else False
        instance_tags = get_instance_tags(instance_id, region)
        
        # Build config
        config = {
            'protect-kernel-defaults' : True,
            'secrets-encryption': True,
            'kube-apiserver-arg': [
                'admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml',
                'audit-log-path=/var/lib/rancher/k3s/server/logs/audit.log',
                'audit-policy-file=/var/lib/rancher/k3s/server/audit.yaml',
                'audit-log-maxage=30',
                'audit-log-maxbackup=10',
                'audit-log-maxsize=100'
            ]
            'kubelet-arg': [
                f'provider-id={provider_id}',
                'max-pods=110',
                'kube-reserved=cpu=100m,memory=500Mi',
                'system-reserved=cpu=100m,memory=500Mi',
                'eviction-hard=memory.available<100Mi,nodefs.available<10%',
            ],
            'node-label': [
                f'topology.kubernetes.io/region={region}',
                f'topology.kubernetes.io/zone={az}',
                f'node.kubernetes.io/instance-type={instance_type}',
                f'node.kubernetes.io/instance-family={instance_family}',
                f'node.kubernetes.io/instance-size={instance_size}',
                f'karpenter.sh/capacity-type={capacity_type}',
                f'kubernetes.io/arch={arch}',
                'kubernetes.io/os=linux',
                # Legacy labels for backward compatibility
                f'failure-domain.beta.kubernetes.io/region={region}',
                f'failure-domain.beta.kubernetes.io/zone={az}',
                f'beta.kubernetes.io/instance-type={instance_type}',
            ]
        }
        
        # Add public IP label only if it exists
        if public_ipv4:
            config['node-label'].insert(5, f'cylzae.com/public-ip={public_ipv4}')
            # Add elastic IP label
            ip_type = 'elastic' if is_eip else 'ephemeral'
            config['node-label'].insert(6, f'cylzae.com/public-ip-type={ip_type}')
        
        # Add punchkicker-role label if tag exists
        if 'punchkicker-role' in instance_tags:
            role_value = instance_tags['punchkicker-role']
            config['node-label'].append(f'cylzae.com/punchkicker-role={role_value}')

        taints = []

        for tag, value in instance_tags.items():
            tag = tag.replace("::", "/")

            if tag.startswith("label/"):
                tag = tag[6:]
                config['node-label'].append(f'{tag}={value}')
            elif tag.startswith("taint/"):
                tag = tag[6:]
                taints.append(f'{tag}={value}')

        if taints:
            config['node-taint'] = taints

        for k, v in config.items():
            if type(v) is list:
                v.sort()
        
        return config
        
    except Exception as e:
        print(f"Error fetching EC2 metadata: {e}", file=sys.stderr)
        print("Make sure you're running on an EC2 instance with IMDSv2 enabled.", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    config = generate_k3s_config()
    
    # Output YAML to stdout
    yaml_output = yaml.dump(config, default_flow_style=False, sort_keys=False)
    print(yaml_output)

if __name__ == '__main__':
    main()
