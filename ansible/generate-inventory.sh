# Required env vars: PROJECT, PLATFORM, ENVIRONMENT, APP_NAME, AWS_DEFAULT_REGION
# Run from the directory containing this script.
set -euo pipefail

PROJECT="${PROJECT:?PROJECT env var is required}"
PLATFORM="${PLATFORM:?PLATFORM env var is required}"
ENVIRONMENT="${ENVIRONMENT:?ENVIRONMENT env var is required}"
APP_NAME="${APP_NAME:?APP_NAME env var is required}"
REGION="${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION env var is required}"

mkdir -p inventories
INVENTORY_FILE="inventories/hosts.yml"

# --- Platform info: SSM bucket name ---
PLATFORM_PARAM_PATH="/${PROJECT}-${PLATFORM}/info"
echo "Fetching platform info from SSM: $PLATFORM_PARAM_PATH"
platform_info=$(aws ssm get-parameter --name "$PLATFORM_PARAM_PATH" --query "Parameter.Value" --output text)

SSM_BUCKET_NAME=$(echo "$platform_info" | jq -r '.s3.state_bucket // empty')
if [[ -z "$SSM_BUCKET_NAME" ]]; then
  echo "s3.state_bucket not found in $PLATFORM_PARAM_PATH" >&2
  exit 1
fi

# --- App info: EC2 instance IDs ---
APP_PARAM_PATH="/${PROJECT}/${PLATFORM}/${ENVIRONMENT}/${APP_NAME}/info"
echo "Fetching app info from SSM: $APP_PARAM_PATH"
app_info=$(aws ssm get-parameter --name "$APP_PARAM_PATH" --query "Parameter.Value" --output text)

hosts_block=""
while IFS= read -r instance_id; do
  [[ -z "$instance_id" ]] && continue
  hosts_block+="    $instance_id:\n      ansible_host: $instance_id\n"
done < <(echo "$app_info" | jq -r '.ec2_instance_ids[]' | sort)

if [[ -z "$hosts_block" ]]; then
  echo "No EC2 instance IDs found at $APP_PARAM_PATH" >&2
  exit 1
fi

vars_block="    ansible_connection: community.aws.aws_ssm
    ansible_aws_ssm_region: ${REGION}
    ansible_aws_ssm_bucket_name: ${SSM_BUCKET_NAME}"

cat > "$INVENTORY_FILE" <<EOF
all:
  vars:
${vars_block}

  hosts:
$(printf '%b' "$hosts_block")
EOF

echo "Generated $INVENTORY_FILE"
cat "$INVENTORY_FILE"
