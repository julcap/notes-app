import os
import re
import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yaml"


class DeploymentPolicyTests(unittest.TestCase):
    maxDiff = None

    def render(self, environment: str, storage_backend: str = "local") -> tuple[str, list[dict]]:
        namespace = f"minutes-{environment}"
        env = {
            **os.environ,
            "DEPLOY_ENVIRONMENT": environment,
            "KUBE_NAMESPACE": namespace,
            "BACKEND_IMAGE": "registry.example/minutes-backend@sha256:" + "a" * 64,
            "FRONTEND_IMAGE": "registry.example/minutes-frontend@sha256:" + "b" * 64,
            "IMAGE_SHA": "1" * 40,
            "APP_DOMAIN": f"{environment}.minutes.example",
            "ACM_CERTIFICATE_ARN": f"arn:aws:acm:us-east-1:111111111111:certificate/{environment}",
            "AWS_REGION": "us-east-1",
            "SES_FROM_EMAIL": f"minutes-{environment}@example.com",
            "SES_ROLE_ARN": f"arn:aws:iam::111111111111:role/minutes-{environment}-ses",
            "FRONTEND_SENTRY_DSN": "",
            "METRICS_ENABLED": "false",
            "STORAGE_BACKEND": storage_backend,
            "S3_BUCKET": f"minutes-{environment}",
            "S3_PREFIX": "attachments/",
            "PURGE_SCHEDULE": "0 3 * * *",
            "REMINDER_SCHEDULE": "* * * * *",
            "DIGEST_SCHEDULE": "0 9 * * 1",
        }
        result = subprocess.run(
            ["bash", "deploy/render.sh"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        return result.stdout, documents

    def test_staging_and_production_render_to_isolated_namespaces(self):
        staging_text, staging = self.render("staging")
        production_text, production = self.render("production")

        for environment, documents in (("staging", staging), ("production", production)):
            namespace = f"minutes-{environment}"
            self.assertGreaterEqual(len(documents), 10)
            for document in documents:
                self.assertIn("apiVersion", document)
                self.assertIn("kind", document)
                self.assertIn("metadata", document)
                if document["kind"] == "Namespace":
                    self.assertEqual(document["metadata"]["name"], namespace)
                else:
                    self.assertEqual(document["metadata"].get("namespace"), namespace)

            secret_names = {
                ref["secretKeyRef"]["name"]
                for document in documents
                for ref in self._nested_secret_refs(document)
            }
            self.assertTrue(secret_names)
            self.assertTrue(all(name.startswith(namespace + "-") for name in secret_names))

            serialized = yaml.safe_dump_all(documents)
            self.assertIn(f"value: {environment}", serialized)
            self.assertIn("registry.example/minutes-backend@sha256:", serialized)
            self.assertIn("registry.example/minutes-frontend@sha256:", serialized)
            self.assertNotIn(
                "minutes-production" if environment == "staging" else "minutes-staging",
                serialized,
            )

        self.assertNotEqual(staging_text, production_text)

    def test_s3_overlays_render_as_valid_isolated_resources(self):
        for environment in ("staging", "production"):
            _, documents = self.render(environment, "s3")
            namespace = f"minutes-{environment}"
            serialized = yaml.safe_dump_all(documents)
            self.assertIn(f"value: minutes-{environment}", serialized)
            self.assertIn("value: attachments/", serialized)
            self.assertNotIn(
                "minutes-production" if environment == "staging" else "minutes-staging",
                serialized,
            )
            for document in documents:
                if document["kind"] != "Namespace":
                    self.assertEqual(document["metadata"].get("namespace"), namespace)

    def test_renderer_fails_closed_when_required_configuration_is_missing(self):
        result = subprocess.run(
            ["bash", "deploy/render.sh"],
            cwd=ROOT,
            env={"PATH": os.environ["PATH"], "DEPLOY_ENVIRONMENT": "staging"},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KUBE_NAMESPACE", result.stderr)

    def test_renderer_requires_an_explicit_storage_backend(self):
        env = {
            **os.environ,
            "DEPLOY_ENVIRONMENT": "staging",
            "KUBE_NAMESPACE": "minutes-staging",
            "BACKEND_IMAGE": "registry.example/backend@sha256:" + "a" * 64,
            "FRONTEND_IMAGE": "registry.example/frontend@sha256:" + "b" * 64,
            "IMAGE_SHA": "1" * 40,
            "APP_DOMAIN": "staging.minutes.example",
            "ACM_CERTIFICATE_ARN": "arn:aws:acm:region:account:certificate/staging",
            "AWS_REGION": "us-east-1",
            "SES_FROM_EMAIL": "staging@example.com",
            "SES_ROLE_ARN": "arn:aws:iam::111111111111:role/staging-ses",
            "PURGE_SCHEDULE": "0 3 * * *",
            "REMINDER_SCHEDULE": "* * * * *",
            "DIGEST_SCHEDULE": "0 9 * * 1",
        }
        result = subprocess.run(
            ["bash", "deploy/render.sh"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STORAGE_BACKEND", result.stderr)

    def test_workflow_has_no_automatic_production_path(self):
        workflow = WORKFLOW_PATH.read_text()
        parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
        triggers = parsed["on"]
        self.assertEqual(
            set(triggers["push"]["branches"]), {"main", "feat/prd-completion"}
        )
        self.assertEqual(
            triggers["workflow_dispatch"]["inputs"]["promotion_sha"]["required"], "true"
        )

        jobs = parsed["jobs"]
        self.assertEqual(jobs["deploy-staging"]["environment"], "staging")
        self.assertIn("refs/heads/main", jobs["deploy-staging"]["if"])
        self.assertEqual(jobs["deploy-production"]["environment"], "production")
        self.assertIn("workflow_dispatch", jobs["deploy-production"]["if"])
        self.assertNotIn("push", jobs["deploy-production"]["if"])
        self.assertIn("validate-production-promotion", jobs["deploy-production"]["needs"])

        production_job = yaml.safe_dump(jobs["deploy-production"])
        self.assertIn("PROMOTION_SHA", production_job)
        self.assertIn("actions/download-artifact", production_job)
        self.assertIn("staging-images.json", production_job)
        self.assertNotIn("describe-images", production_job)
        self.assertNotIn("docker/build-push-action", production_job)
        self.assertIn("STAGING_DEPLOY_ENABLED", workflow)
        self.assertIn("imageTagMutability", workflow)
        self.assertIn("IMMUTABLE", workflow)
        self.assertIsNone(re.search(r"uses:\s+[^\s]+@v\d", workflow))

    def test_promotion_requires_a_successful_main_staging_run_for_exact_sha(self):
        workflow = WORKFLOW_PATH.read_text()
        self.assertIn("listWorkflowRuns", workflow)
        self.assertIn("branch: 'main'", workflow)
        self.assertIn("event: 'push'", workflow)
        self.assertIn("status: 'success'", workflow)
        self.assertIn("run.head_sha === promotionSha", workflow)
        self.assertRegex(workflow, r"\^\[0-9a-f\]\{40\}\$")
        self.assertIn("PROMOTION_SHA_INPUT", workflow)
        self.assertIn("process.env.PROMOTION_SHA_INPUT", workflow)
        self.assertNotIn("const promotionSha = '${{ inputs.promotion_sha }}'", workflow)
        self.assertIn("staging_run_id", workflow)
        self.assertIn("actions/upload-artifact", workflow)
        self.assertIn("group: minutes-staging", workflow)
        self.assertIn("group: minutes-production", workflow)
        self.assertGreaterEqual(workflow.count("github.ref == 'refs/heads/main'"), 3)

    def test_operational_targets_follow_environment_namespace(self):
        prometheus = (ROOT / "monitoring" / "prometheus.yml.template").read_text()
        self.assertIn("backend.${KUBE_NAMESPACE}.svc.cluster.local:8000", prometheus)
        self.assertNotIn("backend.minutes.svc.cluster.local", prometheus)

        operational_docs = "\n".join(
            (ROOT / path).read_text()
            for path in (
                "AUTH.md",
                "monitoring/README.md",
                "docs/PRD/04 Production Readiness/06 - done - Error tracking (Sentry).md",
                "docs/PRD/04 Production Readiness/08 - done - Metrics.md",
            )
        )
        for stale in (
            "`minutes-secrets`",
            "`minutes-oauth`",
            "`minutes-observability`",
            "serviceaccount:minutes:minutes-backend",
            "backend.minutes.svc.cluster.local",
        ):
            self.assertNotIn(stale, operational_docs)

    def test_migration_waits_before_application_rollout(self):
        workflow = WORKFLOW_PATH.read_text()
        wait = workflow.index(
            'kubectl -n "$KUBE_NAMESPACE" wait --for=condition=complete "job/$MIGRATION_JOB_NAME"'
        )
        apply_app = workflow.index('kubectl apply -f "$RENDER_DIR/app.yaml"')
        rollout = workflow.index("rollout status deployment/backend")
        self.assertLess(wait, apply_app)
        self.assertLess(apply_app, rollout)

    @staticmethod
    def _nested_secret_refs(value):
        if isinstance(value, dict):
            if "secretKeyRef" in value:
                yield value
            for nested in value.values():
                yield from DeploymentPolicyTests._nested_secret_refs(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from DeploymentPolicyTests._nested_secret_refs(nested)


if __name__ == "__main__":
    unittest.main()
