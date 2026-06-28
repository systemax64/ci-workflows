SSM_PREFIX="$1"

if [ -z "$SSM_PREFIX" ]; then
    echo "ERROR: SSM prefix argument is required"
    exit 1
fi

# Extract required keys from .env.example (comma-separated)
REQUIRED_ENV_KEYS=$(awk -F '=' '!/^#/ && NF > 0 { sep = (NR > 1 ? "," : ""); printf "%s%s", sep, $1 }' .env.example)

if [ -z "$REQUIRED_ENV_KEYS" ]; then
    echo "ERROR: No keys found in .env.example"
    exit 1
fi

# Fetch parameters JSON from AWS SSM
ENV_PARAMS=$(aws ssm get-parameter --with-decryption \
    --name "$SSM_PREFIX/env_params" \
    --query 'Parameter.Value' --output text)

if [ -z "$ENV_PARAMS" ]; then
    echo "ERROR: SSM parameter is empty or could not be fetched"
    exit 1
fi

# Validate JSON
DEFINED_ENV_KEYS=$(jq '.' <<< "$ENV_PARAMS")
if [ -z "$DEFINED_ENV_KEYS" ]; then
    echo "ERROR: SSM parameter is not valid JSON"
    exit 1
fi

# Build sorted lists for comparison
REQUIRED_KEYS_SORTED=$(echo "$REQUIRED_ENV_KEYS" | tr ',' '\n' | sort -u)
SSM_KEYS_SORTED=$(jq -r 'keys[]' <<< "$DEFINED_ENV_KEYS" | sort -u)

# Check 1: Required keys missing from SSM
MISSING_KEYS=$(comm -23 <(echo "$REQUIRED_KEYS_SORTED") <(echo "$SSM_KEYS_SORTED"))

# Check 2: Extra keys in SSM not present in .env.example
EXTRA_KEYS=$(comm -13 <(echo "$REQUIRED_KEYS_SORTED") <(echo "$SSM_KEYS_SORTED"))

HAS_ERROR=0

if [ -n "$MISSING_KEYS" ]; then
    echo "ERROR: The following keys are required by .env.example but missing in SSM:"
    echo "$MISSING_KEYS" | sed 's/^/  - /'
    HAS_ERROR=1
fi

if [ -n "$EXTRA_KEYS" ]; then
    echo "ERROR: The following keys exist in SSM but are not declared in .env.example:"
    echo "$EXTRA_KEYS" | sed 's/^/  - /'
    HAS_ERROR=1
fi

if [ "$HAS_ERROR" -eq 1 ]; then
    exit 1
fi

# All checks passed — build the .env file
IFS=','
for ENV_KEY in $REQUIRED_ENV_KEYS
do
    ENV_VALUE=$(jq -r --arg k "$ENV_KEY" '.[$k]' <<< "$DEFINED_ENV_KEYS")
    echo "$ENV_KEY=$ENV_VALUE" >> .env
done
unset IFS

# Export a short hash of the .env for use as a cache/version key
echo "ENV_HASH=$(md5sum .env | cut -c 1-5)" >> $GITHUB_ENV

echo ".env file built successfully with $(wc -l < .env) variables"
