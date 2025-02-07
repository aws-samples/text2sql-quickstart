from datetime import datetime
from typing import Dict, Any, Optional
import streamlit as st
import time
import json
import boto3
from config import AWS_REGION

class PerformanceMonitor:
    def __init__(self):
        """성능 모니터링 초기화"""
        self.metrics = []
        self.cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
        self.last_operation = None  # 마지막 작업 정보 저장용

    def start_operation(self, operation_name: str) -> str:
        """작업 시작 시간 기록"""
        operation_id = f"{operation_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        metric = {
            "operation_id": operation_id,
            "operation_name": operation_name,
            "start_time": datetime.now(),
            "status": "running"
        }
        self.metrics.append(metric)
        self.last_operation = metric  # 마지막 작업 정보 저장
        return operation_id

    def end_operation(self, operation_id: str, result: Optional[Dict] = None) -> None:
        """작업 종료 시간 기록 및 지표 전송"""
        for metric in self.metrics:
            if metric["operation_id"] == operation_id:
                end_time = datetime.now()
                duration = (end_time - metric["start_time"]).total_seconds()
                metric.update({
                    "end_time": end_time,
                    "duration": duration,
                    "status": "completed",
                    "result": result
                })
                self.last_operation = metric  # 마지막 작업 정보 업데이트

                # CloudWatch에 지표 전송
                try:
                    self.cloudwatch.put_metric_data(
                        Namespace='TextToSQL',
                        MetricData=[
                            {
                                'MetricName': f"{metric['operation_name']}_Duration",
                                'Value': duration,
                                'Unit': 'Seconds',
                                'Dimensions': [
                                    {
                                        'Name': 'OperationType',
                                        'Value': metric['operation_name']
                                    }
                                ]
                            }
                        ]
                    )
                except Exception as e:
                    st.warning(f"CloudWatch 지표 전송 실패: {str(e)}")

    def get_last_duration(self) -> float:
        """가장 최근 작업의 실행 시간 반환"""
        if self.last_operation and "duration" in self.last_operation:
            return self.last_operation["duration"]
        return 0.0

    def get_last_operation(self) -> Optional[Dict]:
        """가장 최근 작업의 정보 반환"""
        return self.last_operation

    def log_error(self, operation_id: str, error: Exception) -> None:
        """오류 정보 기록"""
        for metric in self.metrics:
            if metric["operation_id"] == operation_id:
                metric.update({
                    "status": "error",
                    "error": str(error),
                    "error_time": datetime.now().isoformat()
                })
                self.last_operation = metric  # 마지막 작업 정보 업데이트

    def get_metrics(self) -> Dict[str, Any]:
        """현재 성능 지표 반환"""
        return {
            "metrics": self.metrics,
            "summary": {
                "total_operations": len(self.metrics),
                "completed": len([m for m in self.metrics if m["status"] == "completed"]),
                "errors": len([m for m in self.metrics if m["status"] == "error"]),
                "average_duration": sum(m.get("duration", 0) for m in self.metrics if "duration" in m) /
                                    len([m for m in self.metrics if "duration" in m]) if self.metrics else 0
            }
        }