from __future__ import annotations

import pendulum

from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="hello_world_dag",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    schedule=None,
    tags=["example"],
) as dag:
    hello_task = BashOperator(
        task_id="hello_task",
        bash_command="echo 'Hello World from Airflow DAG!'",
    )

    bye_task = BashOperator(
        task_id="bye_task",
        bash_command="echo 'Bye from Airflow DAG!'",
    )

    hello_task >> bye_task
