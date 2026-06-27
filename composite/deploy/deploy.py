import time
import argparse
import boto3

from maintenance import switch_maintenance

parser = argparse.ArgumentParser(description='Update ECS service with new container image.')

# TODO: Use double dash args
parser.add_argument('ecs_cluster_name', help='The name of the ECS cluster')
parser.add_argument('ecs_service_name', help='The name of the ECS service')
parser.add_argument('new_image_uri', help='The new container image URI to deploy')
parser.add_argument('enable_maintenance_mode', help='Whether to enable maintenance mode before deployment and disable it after deployment.')
parser.add_argument('ctnr_command', help='Semicolon delimited list of commands to run in the container')

args = parser.parse_args()

ECS_CLUSTER_NAME        = args.ecs_cluster_name
ECS_SERVICE_NAME        = args.ecs_service_name
NEW_IMAGE_URI           = args.new_image_uri
ENABLE_MAINTENANCE_MODE = args.enable_maintenance_mode.lower() == 'true'
CTNR_COMMAND            = [cmd.strip() for cmd in args.ctnr_command.split(";") if cmd.strip()]

client = boto3.client('ecs')

ecs_services = client.describe_services(cluster=ECS_CLUSTER_NAME, services=[ECS_SERVICE_NAME])
if len(ecs_services["services"]) == 0:
    print("Service not found, exiting.")
    exit(1)

ecs_service             = ecs_services["services"][0]
service_rollout_state   = ecs_service["deployments"][0]["rolloutState"]
if service_rollout_state == "IN_PROGRESS":
    print("Service is already being updated, exiting.")
    exit(1)

current_ecs_task_definition = client.describe_task_definition(taskDefinition=ecs_service["taskDefinition"])["taskDefinition"]
current_image_uri           = current_ecs_task_definition["containerDefinitions"][0]["image"]
if current_image_uri == NEW_IMAGE_URI:
    print("No updates are to be performed, exiting.")
    exit(0)

if ENABLE_MAINTENANCE_MODE:
    ecs_service_tags    = response = client.list_tags_for_resource(resourceArn=ecs_service["serviceArn"])["tags"]
    tag_dict            = {tag["key"]: tag["value"] for tag in ecs_service_tags}
    project_name        = tag_dict["Project"]
    deployment_name     = tag_dict["Deployment"]
    application         = tag_dict["Application"]
    environment         = tag_dict["Environment"]

current_ecs_task_definition["containerDefinitions"][0]["image"] = NEW_IMAGE_URI
current_ecs_task_definition["containerDefinitions"][0]["command"] = ["ecs-stack-entrypoint"] + CTNR_COMMAND
for i in ["taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt", "registeredBy"]:
    del(current_ecs_task_definition[i])

new_ecs_task_definition = client.register_task_definition(**current_ecs_task_definition)

if ENABLE_MAINTENANCE_MODE:
    print("Switching maintenance...")
    switch_maintenance(project_name, deployment_name, f"{project_name}-{environment}-{application}-maintenance-rule", f"{project_name}-{environment}-{application}-app-rule", "on")

updated_service         = client.update_service(cluster=ECS_CLUSTER_NAME, service=ECS_SERVICE_NAME, taskDefinition=new_ecs_task_definition["taskDefinition"]["taskDefinitionArn"])

print("Serivce deployment initiated successfully\n━ Waiting for service to stabilize...")
while True:
    service                 = client.describe_services(cluster=ECS_CLUSTER_NAME, services=[ECS_SERVICE_NAME])["services"][0]
    deployment              = service["deployments"][0]

    deployment_status       = deployment["status"]
    rollout_state           = deployment["rolloutState"]
    rollout_state_reason    = deployment["rolloutStateReason"]

    match rollout_state:
        case "IN_PROGRESS":
            print("━━ Deployment currently in progress...")
        case "COMPLETED":
            print("━ Deployment completed")
            break
        case "FAILED":
            print(f"━ Deployment failed with reason: {rollout_state_reason}")
            exit(1)

    time.sleep(10)

deployment_result           = client.list_service_deployments(cluster=ECS_CLUSTER_NAME, service=ECS_SERVICE_NAME)["serviceDeployments"][0]
deployment_status           = deployment_result["status"]

if deployment_status != "SUCCESSFUL":
    print(f"❯❯❯❯ Deployment status: {deployment_status}")
    print(f"❯❯❯❯ Deployment status reason: {deployment_result.get('statusReason')}")
    exit(1)

if ENABLE_MAINTENANCE_MODE:
    print("Switching maintenance...")
    switch_maintenance(project_name, deployment_name, f"{project_name}-{environment}-{application}-maintenance-rule", f"{project_name}-{environment}-{application}-app-rule", "off")
print(f"❯❯❯❯ Deployment status: {deployment_status}")
