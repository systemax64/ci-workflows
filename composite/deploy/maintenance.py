import boto3

def switch_maintenance(
    project_tag_value: str,
    deployment_tag_value: str,
    maintenance_rule_name: str,
    app_rule_name: str,
    maintenance: str
) -> None:
    PROJECT_TAG_VALUE       = project_tag_value
    DEPLOYMENT_TAG_VALUE    = deployment_tag_value
    MAINTENANCE_RULE_NAME   = maintenance_rule_name
    APP_RULE_NAME           = app_rule_name
    MAINTENANCE             = maintenance
    PORT                    = 443

    if MAINTENANCE not in ["on", "off"]:
        print(f"Invalid maintenance state: {MAINTENANCE}. Use 'on' or 'off'.")
        exit(1)

    client = boto3.client('elbv2')

    lb_arn          = ""
    load_balancers  = client.describe_load_balancers()

    if len(load_balancers["LoadBalancers"]) == 0:
        print("No load balancers found, exiting.")
        exit(1)

    for lb in load_balancers["LoadBalancers"]:
        lb_tags     = client.describe_tags(ResourceArns=[lb["LoadBalancerArn"]])["TagDescriptions"][0]["Tags"]
        tag_dict    = {tag["Key"]: tag["Value"] for tag in lb_tags}

        project     = tag_dict.get("Project")
        deployment  = tag_dict.get("Deployment")

        if project == PROJECT_TAG_VALUE and deployment == DEPLOYMENT_TAG_VALUE:
            lb_arn = lb["LoadBalancerArn"]
            break

    if lb_arn == "":
        print("No load balancer found with provided project and deployment tag values, exiting.")
        exit(1)

    print(f"━ Found Load Balancer: {lb_arn}")


    lb_listeners = client.describe_listeners(
        LoadBalancerArn=lb_arn,
    )

    if len(lb_listeners["Listeners"]) == 0:
        print("No listeners found for load balancer, exiting.")
        exit(1)

    listener_arn = ""
    for listener in lb_listeners["Listeners"]:
        if listener["Port"] == PORT:
            listener_arn = listener["ListenerArn"]
            break

    if listener_arn == "":
        print(f"No listener found on port {PORT}, exiting")
        exit(1)

    print(f"━ Found {PORT} listenr: {listener_arn}")


    rules = client.describe_rules(ListenerArn=listener_arn)

    app_rule_arn                    = ""
    maintenance_rule_arn            = ""
    maintenance_rule_priority       = ""
    range_arr                       = []

    for rule in rules["Rules"]:
        rule_tags   = client.describe_tags(ResourceArns=[rule["RuleArn"]])["TagDescriptions"][0]["Tags"]
        tag_dict    = {tag["Key"]: tag["Value"] for tag in rule_tags}

        name = tag_dict.get("Name")

        if name == MAINTENANCE_RULE_NAME:
            maintenance_rule_arn = rule["RuleArn"]
            maintenance_rule_priority = rule["Priority"]

        if name == APP_RULE_NAME:
            app_rule_arn = rule["RuleArn"]
            range_arr = tag_dict["Range"].split("-")
        
    if app_rule_arn == "" or maintenance_rule_arn == "":
        print("Either app rule or maintenance rule was not found, exiting.")
        exit(1)

    if MAINTENANCE == "on":
        if maintenance_rule_priority == range_arr[0]:
            print("❯❯❯❯ Maintenance rule is already active.")
        else:
            print("Activating maintenance...")
            client.set_rule_priorities(RulePriorities=[{'RuleArn': app_rule_arn, 'Priority': int(range_arr[2])}])
            client.set_rule_priorities(RulePriorities=[{'RuleArn': maintenance_rule_arn, 'Priority': int(range_arr[0])}])
            print("━ Maintenance rule activated.")

            return

    if MAINTENANCE == "off":
        if maintenance_rule_priority == range_arr[1]:
            print("❯❯❯❯ Maintenance rule is already inactive.")
        else:
            print("Deactivating maintenance...")
            client.set_rule_priorities(RulePriorities=[{'RuleArn': maintenance_rule_arn, 'Priority': int(range_arr[1])}])
            client.set_rule_priorities(RulePriorities=[{'RuleArn': app_rule_arn, 'Priority': int(range_arr[0])}])
            print("━ Maintenance deactivated.")

            return
