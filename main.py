import os
import sys
import oyaml as yaml
import json


class GithubAction():

    def __init__(self):
        pass

    def gh_debug(self, message):
        print(f"::debug::{message}")

    def gh_warning(self, message):
        print(f"::warning::{message}")

    def gh_error(self, message):
        print(f"::error::{message}")

    def gh_status(self, parameter, value):
        print(f"::set-output name={parameter}::{value}")


class APIConnectQualityCheck(GithubAction):

    def __init__(self):
        self.quality_errors = []


    def load_yaml(self, filename, encoding='utf-8'):
        with open(filename, 'r', encoding=encoding) as file:
            return yaml.safe_load(file)


    def safeget(self, dct, *keys):
        for key in keys:
            try:
                dct = dct[key]
            except KeyError:
                return None
        return dct


    def check(self, assertion, message, artifact, rule):
        if not assertion:
            self.quality_errors.append(f"{rule}: {artifact}: {message}")
            self.gh_warning(f"{rule}: {artifact}: {message}")


    def check_product(self, product_path):

        product = self.load_yaml(product_path)
        product_name = product['info']['title']

        # Comprobar que la versión del producto se compone solo de major y minor
        version = product['info']['version']
        self.check(rule="P001",
            assertion=len(version.split('.')) == 2,
            artifact=product_name,
            message=f"El código de versión '{version}' no es correcto.")

        # Comprobar los planes de suscripción
        self.check(rule="P002",
            assertion=len(product['plans']) == 3,
            artifact=product_name,
            message=f"El número de planes de suscripción no es correcto.")

        # Comprobar la visibilidad del producto
        self.check(rule="P003",
            assertion=self.safeget(product, 'visibility', 'view', 'type') == "public",
            artifact=product_name,
            message=f"La visibilidad del producto debe ser pública.")

        # Comprobar la configuración de suscripción al producto
        self.check(rule="P004",
            assertion=self.safeget(product, 'visibility', 'subscribe', 'type') == "authenticated",
            artifact=product_name,
            message=f"La suscripción´del producto debe ser solo para usuarios autenticados.")

        # Comprobar el formato de referencia de APIs
        for api_name in product['apis']:
            api = product['apis'][api_name]
            self.check(rule="P005",
                assertion='name' not in api,
                artifact=product_name,
                message=f"El api {api_name} está referenciado por nombre.")

            api_path = os.path.join(os.path.dirname(product_path),api['$ref'])

            self.check(rule="P006",
                assertion=os.path.exists(api_path),
                artifact=product_name,
                message=f"El API ''{api_name}' referenciado no existe.")

            self.check_api(api_path)

    def check_api(self, api_path):

        api = self.load_yaml(api_path)

        api_name = f"{api['info']['title']} ({api['info']['x-ibm-name']})"

        # Comprobar que la versión del producto se compone solo de major y minor
        version = api['info']['version']
        self.check(rule="A001",
            assertion=len(version.split('.')) == 2,
            artifact=api_name,
            message=f"El código de versión '{version}' no es correcto.")

        # Comprobar el esquema de seguridad
        security_schema = {
            "type": "apiKey",
            "in": "header",
            "name": "X-IBM-Client-Id"
        }
        client_id_header = self.safeget(api, 'securityDefinitions', 'clientIdHeader')
        self.check(rule="A002",
            assertion=client_id_header is not None,
            artifact=api_name,
            message=f"El esquema de seguridad no está definido correctamente.")
        self.check(rule="A003",
            assertion=client_id_header == security_schema,
            artifact=api_name,
            message=f"El esquema de seguridad no está definido correctamente.")

        # Comprobar el activity log
        activity_schema = {
            "success-content": "payload",
            "error-content": "payload",
            "enabled": True
        }
        activty_log = self.safeget(api, 'x-ibm-configuration', 'activity-log')
        self.check(rule="A004",
            assertion=activty_log is not None,
            artifact=api_name,
            message=f"El esquema de seguridad no está definido correctamente.")
        self.check(rule="A005",
            assertion=activty_log == activity_schema,
            artifact=api_name,
            message=f"El almacenamiento de actividad no está definido correctamente.")

        # Comprobar las políticas
        for policy in api['x-ibm-configuration']['assembly']:
            self.check_assembly(api['x-ibm-configuration']['assembly'][policy])


    def check_assembly(self, assembly):
        for policy in assembly:
            self.check_policy(policy)


    def check_policy(self, policy):
        policy_type = list(policy.keys())[0]
        policy = policy[policy_type]

        self.gh_debug(f"Checking policy {policy.get('title')}")

        if policy_type == "gatewayscript":
            pass
        elif policy_type == "switch":
            for case in [p for p in policy['case'] if "condition" in p]:
                self.check_assembly(case['execute'])
            for case in [p for p in policy['case'] if "otherwise" in p]:
                self.check_assembly(case['otherwise'])
        elif policy_type == "invoke":
            self.check(rule="????",
                assertion=policy['verb'] != "keep",
                artifact=policy['title'],
                message="El verbo de las políticas invoke debe especificarse de forma explícita.")


    def run(self):
        product_path = os.getenv("INPUT_PRODUCTFILE")

        if not product_path or not os.path.exists(product_path):
            self.gh_error(f"No existe el fichero {product_path}")
            self.gh_status("result", "error")
            exit(99)

        self.check_product(product_path)

        if not self.quality_errors:
            self.gh_status("result", "ok")
            exit(0)
        else:
            self.gh_status("result", "warning")
            exit(99)


if __name__ == "__main__":

    action = APIConnectQualityCheck()
    action.run()