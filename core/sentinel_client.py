import os
import logging
from datetime import datetime, timezone
from azure.identity import ClientSecretCredential
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError

logger = logging.getLogger(__name__)


class SentinelClient:
    def __init__(self):
        self.enabled = all([
            os.getenv("AZURE_TENANT_ID"),
            os.getenv("AZURE_CLIENT_ID"),
            os.getenv("AZURE_CLIENT_SECRET"),
            os.getenv("SENTINEL_DCE_ENDPOINT"),
            os.getenv("SENTINEL_DCR_IMMUTABLE_ID"),
        ])
        if self.enabled:
            credential = ClientSecretCredential(
                tenant_id=os.getenv("AZURE_TENANT_ID"),
                client_id=os.getenv("AZURE_CLIENT_ID"),
                client_secret=os.getenv("AZURE_CLIENT_SECRET"),
            )
            self.client = LogsIngestionClient(
                endpoint=os.getenv("SENTINEL_DCE_ENDPOINT"),
                credential=credential,
            )
            self.dcr_id = os.getenv("SENTINEL_DCR_IMMUTABLE_ID")
            self.table = os.getenv("SENTINEL_TABLE", "PHIMaskingJobs_CL")
            logger.info("Sentinel client initialized")
        else:
            logger.warning("Sentinel env vars not set — audit events will not be sent")

    def send_job_event(
        self,
        job_id: str,
        status: str,
        rows_processed: int,
        leaked_rows: int,
        source_file: str,
    ):
        if not self.enabled:
            return
        body = [{
            "TimeGenerated": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "status": status,
            "rows_processed": rows_processed,
            "leaked_rows": leaked_rows,
            "phi_leakage_detected": leaked_rows > 0,
            "source_file": source_file,
        }]
        try:
            self.client.upload(
                rule_id=self.dcr_id,
                stream_name=f"Custom-{self.table}",
                logs=body,
            )
            logger.info("Sentinel event sent: job=%s status=%s leaked=%d", job_id, status, leaked_rows)
        except HttpResponseError as e:
            logger.error("Sentinel upload failed: %s", e)


sentinel = SentinelClient()
