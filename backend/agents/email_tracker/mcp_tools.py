import os
import sys
import json
import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlencode

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.a2ui_builders import (
    card, text, table, metric_card, alert, row, column,
    divider, create_response, Node,
)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Please install with: pip install requests")
    requests = None

try:
    from fuzzywuzzy import fuzz
except ImportError:
    print("WARNING: 'fuzzywuzzy' package not installed. Install for better deduplication: pip install fuzzywuzzy python-Levenshtein")
    fuzz = None

REQUIRED_CREDENTIALS = [
    {
        "key": "MS_GRAPH_CLIENT_ID",
        "label": "Microsoft Graph Client ID",
        "description": "OAuth 2.0 Client ID from Azure App Registration",
        "required": True,
        "type": "oauth_client_id"
    },
    {
        "key": "MS_GRAPH_CLIENT_SECRET",
        "label": "Microsoft Graph Client Secret",
        "description": "OAuth 2.0 Client Secret from Azure App Registration",
        "required": True,
        "type": "oauth_client_secret"
    },
    {
        "key": "MS_GRAPH_TENANT_ID",
        "label": "Microsoft Graph Tenant ID",
        "description": "Azure AD Tenant/Directory ID",
        "required": True,
        "type": "api_key"
    }
]

class GraphAPIClient:
    def __init__(self, credentials: Dict[str, str]):
        self.client_id = credentials.get("MS_GRAPH_CLIENT_ID", "")
        self.client_secret = credentials.get("MS_GRAPH_CLIENT_SECRET", "")
        self.tenant_id = credentials.get("MS_GRAPH_TENANT_ID", "")
        self.access_token = None
        self.token_expiry = None
        self.base_url = "https://graph.microsoft.com/v1.0"
        
    def _get_access_token(self) -> Optional[str]:
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            return None
            
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default"
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            self.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 300)
            return self.access_token
        except Exception as e:
            print(f"Token acquisition failed: {e}")
            return None
    
    def _ensure_token(self) -> bool:
        if not self.access_token or (self.token_expiry and datetime.now(timezone.utc) >= self.token_expiry):
            return self._get_access_token() is not None
        return True
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        if not self._ensure_token():
            return None
            
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            print(f"Graph API request failed: {e}")
            return None
    
    def get_recent_emails(self, days: int = 7, top: int = 50) -> List[Dict]:
        since_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        endpoint = f"/me/messages?$filter=receivedDateTime ge {since_date}&$top={top}&$orderby=receivedDateTime desc&$select=id,subject,bodyPreview,body,from,receivedDateTime,webLink"
        
        result = self._make_request("GET", endpoint)
        if result and "value" in result:
            return result["value"]
        return []
    
    def get_todo_tasks(self, list_name: str = "Tasks") -> List[Dict]:
        lists_result = self._make_request("GET", "/me/todo/lists")
        if not lists_result or "value" not in lists_result:
            return []
        
        task_list_id = None
        for lst in lists_result["value"]:
            if lst.get("displayName") == list_name:
                task_list_id = lst.get("id")
                break
        
        if not task_list_id:
            return []
        
        tasks_result = self._make_request("GET", f"/me/todo/lists/{task_list_id}/tasks?$filter=status ne 'completed'")
        if tasks_result and "value" in tasks_result:
            return tasks_result["value"]
        return []
    
    def create_todo_task(self, title: str, notes: str = "", list_name: str = "Tasks") -> Optional[Dict]:
        lists_result = self._make_request("GET", "/me/todo/lists")
        if not lists_result or "value" not in lists_result:
            return None
        
        task_list_id = None
        for lst in lists_result["value"]:
            if lst.get("displayName") == list_name:
                task_list_id = lst.get("id")
                break
        
        if not task_list_id:
            return None
        
        task_data = {
            "title": title,
            "body": {
                "content": notes,
                "contentType": "text"
            }
        }
        
        result = self._make_request("POST", f"/me/todo/lists/{task_list_id}/tasks", json=task_data)
        return result

class LLMProcessor:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
    
    def extract_tasks_from_email(self, email_body: str, email_subject: str = "") -> List[Dict]:
        if not email_body:
            return []
        
        cleaned_body = self._clean_email_content(email_body)
        
        prompt = f"""Analyze this email and extract any actionable tasks, to-do items, or deadlines mentioned.
        Return ONLY a valid JSON array of objects, each with these fields:
        - "title": A concise task description (max 100 chars)
        - "description": More details about the task (optional)
        - "deadline": ISO date string if deadline mentioned, else null
        - "priority": "high", "medium", or "low" based on urgency cues
        
        Email Subject: {email_subject}
        Email Body: {cleaned_body[:2000]}
        
        Example output: [{{"title": "Submit Q3 report", "description": "Email to manager by Friday", "deadline": "2024-12-15", "priority": "high"}}]
        
        JSON array:"""
        
        try:
            if self.llm_client:
                response = self.llm_client.generate(prompt)
            else:
                response = self._mock_llm_response(cleaned_body, email_subject)
            
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                tasks = json.loads(json_match.group())
                return tasks if isinstance(tasks, list) else []
        except Exception as e:
            print(f"LLM processing failed: {e}")
        
        return []
    
    def _clean_email_content(self, content: str) -> str:
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'https?://\S+', '[URL]', content)
        return content.strip()
    
    def _mock_llm_response(self, body: str, subject: str) -> str:
        keywords = ["please", "need", "required", "submit", "send", "complete", "review", "follow up", "action", "todo", "task"]
        tasks = []
        
        sentences = re.split(r'[.!?]+', body)
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in keywords):
                title = sentence.strip()[:80]
                if len(title) > 10:
                    tasks.append({
                        "title": title,
                        "description": f"From email: {subject}",
                        "deadline": None,
                        "priority": "medium"
                    })
        
        return json.dumps(tasks[:3])

class TaskDeduplicator:
    def __init__(self, similarity_threshold: int = 85):
        self.similarity_threshold = similarity_threshold
    
    def is_duplicate(self, new_task: Dict, existing_tasks: List[Dict]) -> bool:
        if not existing_tasks:
            return False
        
        new_title = new_task.get("title", "").lower().strip()
        if not new_title:
            return False
        
        for existing in existing_tasks:
            existing_title = existing.get("title", "").lower().strip()
            
            if fuzz:
                similarity = fuzz.ratio(new_title, existing_title)
                if similarity >= self.similarity_threshold:
                    return True
            else:
                if new_title == existing_title:
                    return True
                
                words_new = set(new_title.split())
                words_existing = set(existing_title.split())
                if words_new and words_existing:
                    overlap = len(words_new.intersection(words_existing)) / len(words_new.union(words_existing))
                    if overlap > 0.6:
                        return True
        
        return False

def get_auth_status(**kwargs) -> Dict[str, Any]:
    """Check Microsoft Graph authentication status and display connection info."""
    try:
        credentials = kwargs.get("_credentials", {})
        
        client_id = credentials.get("MS_GRAPH_CLIENT_ID", "")
        tenant_id = credentials.get("MS_GRAPH_TENANT_ID", "")
        client_secret = credentials.get("MS_GRAPH_CLIENT_SECRET", "")
        
        has_client_id = bool(client_id)
        has_tenant_id = bool(tenant_id)
        has_client_secret = bool(client_secret)
        
        auth_status = "Connected" if all([has_client_id, has_tenant_id, has_client_secret]) else "Not Connected"
        status_color = "success" if auth_status == "Connected" else "error"
        
        components = [
            card("Microsoft Graph Authentication Status", [
                row([
                    metric_card("Connection Status", auth_status, variant=status_color),
                    metric_card(
                        "Credentials Configured",
                        f"{sum([has_client_id, has_tenant_id, has_client_secret])}/3",
                        subtitle="Client ID, Tenant ID, Client Secret"
                    )
                ]),
                divider(),
                table(
                    ["Credential", "Status"],
                    [
                        ["Client ID", "✓ Configured" if has_client_id else "✗ Missing"],
                        ["Tenant ID", "✓ Configured" if has_tenant_id else "✗ Missing"],
                        ["Client Secret", "✓ Configured" if has_client_secret else "✗ Missing"]
                    ]
                ),
                alert(
                    "Using client credentials flow. Ensure your Azure App has 'Application' permissions (not delegated) for Microsoft Graph.",
                    variant="info"
                )
            ])
        ]

        return create_response(components, data={
            "auth_status": auth_status,
            "has_client_id": has_client_id,
            "has_tenant_id": has_tenant_id,
            "has_client_secret": has_client_secret
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to check auth status: {str(e)}", variant="error")
        )

def fetch_recent_emails(days: int = 7, limit: int = 20, **kwargs) -> Dict[str, Any]:
    """Fetch recent emails from Outlook inbox with optional filtering."""
    try:
        if requests is None:
            return create_response(
                alert("The 'requests' package is required. Please install it: pip install requests", variant="error")
            )

        credentials = kwargs.get("_credentials", {})
        client = GraphAPIClient(credentials)

        emails = client.get_recent_emails(days=days, top=limit)

        if not emails:
            return create_response(
                alert(f"No emails found from the past {days} days.", variant="info")
            )

        email_rows = []
        for email in emails[:10]:
            from_info = email.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            subject = email.get("subject", "No Subject")
            received = email.get("receivedDateTime", "")
            if received:
                try:
                    dt = datetime.fromisoformat(received.replace('Z', '+00:00'))
                    received = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass

            email_rows.append([
                from_info[:30] + ("..." if len(from_info) > 30 else ""),
                subject[:50] + ("..." if len(subject) > 50 else ""),
                received,
                str(len(email.get("bodyPreview", "")))
            ])

        components = [
            card(f"Recent Emails (Past {days} days)", [
                metric_card("Total Emails", str(len(emails)), subtitle=f"Showing first {min(10, len(emails))}"),
                table(["From", "Subject", "Received", "Preview Length"], email_rows),
                text(f"Fetched {len(emails)} emails from the past {days} days.", variant="caption")
            ])
        ]

        return create_response(components, data={
            "total_emails": len(emails),
            "sample_emails": emails[:5],
            "fetch_date": datetime.now().isoformat()
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to fetch emails: {str(e)}", variant="error")
        )

def analyze_email_for_tasks(email_id: str = "latest", **kwargs) -> Dict[str, Any]:
    """Analyze a specific email or the latest email to extract actionable tasks."""
    try:
        if requests is None:
            return create_response(
                alert("The 'requests' package is required. Please install it: pip install requests", variant="error")
            )

        credentials = kwargs.get("_credentials", {})
        client = GraphAPIClient(credentials)

        if email_id == "latest":
            emails = client.get_recent_emails(days=1, top=1)
            if not emails:
                return create_response(
                    alert("No recent emails found.", variant="info")
                )
            email = emails[0]
        else:
            email_result = client._make_request("GET", f"/me/messages/{email_id}")
            if not email_result:
                return create_response(
                    alert(f"Email with ID {email_id} not found.", variant="error")
                )
            email = email_result

        subject = email.get("subject", "No Subject")
        body_content = email.get("body", {}).get("content", "")
        if not body_content:
            body_content = email.get("bodyPreview", "")

        processor = LLMProcessor()
        extracted_tasks = processor.extract_tasks_from_email(body_content, subject)

        task_rows = []
        for i, task in enumerate(extracted_tasks, 1):
            deadline = task.get("deadline", "Not specified")
            priority = task.get("priority", "medium").capitalize()
            task_rows.append([
                str(i),
                task.get("title", "Untitled")[:60],
                task.get("description", "")[:40] + ("..." if len(task.get("description", "")) > 40 else ""),
                deadline,
                priority
            ])

        components = [
            card("Email Task Analysis", [
                text(f"Subject: {subject}", variant="subtitle"),
                card("Email Preview", [
                    text(body_content[:500] + ("..." if len(body_content) > 500 else ""), variant="body"),
                    divider(),
                    text(f"Full length: {len(body_content)} characters", variant="caption")
                ], collapsible=True, default_open=False),
                divider(),
                metric_card("Tasks Extracted", str(len(extracted_tasks)), subtitle="Actionable items found")
            ])
        ]

        if extracted_tasks:
            components.append(
                card("Extracted Tasks", [
                    table(["#", "Title", "Description", "Deadline", "Priority"], task_rows)
                ])
            )
        else:
            components.append(
                alert("No actionable tasks were found in this email.", variant="info")
            )

        return create_response(components, data={
            "email_id": email.get("id"),
            "email_subject": subject,
            "tasks_extracted": extracted_tasks,
            "analysis_date": datetime.now().isoformat()
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to analyze email: {str(e)}", variant="error")
        )

def get_current_todo_tasks(list_name: str = "Tasks", **kwargs) -> Dict[str, Any]:
    """Fetch current active tasks from Microsoft To Do."""
    try:
        if requests is None:
            return create_response(
                alert("The 'requests' package is required. Please install it: pip install requests", variant="error")
            )

        credentials = kwargs.get("_credentials", {})
        client = GraphAPIClient(credentials)

        tasks = client.get_todo_tasks(list_name)

        if not tasks:
            return create_response(
                alert(f"No active tasks found in '{list_name}' list.", variant="info")
            )

        task_rows = []
        for task in tasks:
            title = task.get("title", "Untitled")
            status = task.get("status", "notStarted").replace("notStarted", "Not Started").replace("inProgress", "In Progress").replace("completed", "Completed")
            created = task.get("createdDateTime", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    created = dt.strftime("%Y-%m-%d")
                except:
                    pass

            body_content = task.get("body", {}).get("content", "")
            preview = body_content[:40] + ("..." if len(body_content) > 40 else "") if body_content else ""

            task_rows.append([
                title[:50] + ("..." if len(title) > 50 else ""),
                status,
                created,
                preview
            ])

        components = [
            card(f"Microsoft To Do Tasks ({list_name})", [
                metric_card("Active Tasks", str(len(tasks)), subtitle="Not completed"),
                table(["Title", "Status", "Created", "Notes Preview"], task_rows),
                text(f"Showing {len(tasks)} active tasks from '{list_name}' list.", variant="caption")
            ])
        ]

        return create_response(components, data={
            "total_tasks": len(tasks),
            "tasks": tasks[:10],
            "list_name": list_name,
            "fetch_date": datetime.now().isoformat()
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to fetch To Do tasks: {str(e)}", variant="error")
        )

def triage_inbox_automated(days: int = 7, email_limit: int = 10, **kwargs) -> Dict[str, Any]:
    """Automated inbox triage: fetch emails, extract tasks, deduplicate, and add to To Do."""
    try:
        if requests is None:
            return create_response(
                alert("The 'requests' package is required. Please install it: pip install requests", variant="error")
            )

        credentials = kwargs.get("_credentials", {})
        client = GraphAPIClient(credentials)
        processor = LLMProcessor()
        deduplicator = TaskDeduplicator()

        progress_components = []

        progress_components.append(text("Step 1: Fetching recent emails...", variant="subtitle"))
        emails = client.get_recent_emails(days=days, top=email_limit)
        progress_components.append(alert(f"Found {len(emails)} emails from past {days} days", variant="info"))

        progress_components.append(divider())
        progress_components.append(text("Step 2: Extracting tasks from emails...", variant="subtitle"))

        all_extracted_tasks = []
        for i, email in enumerate(emails[:5], 1):
            subject = email.get("subject", "No Subject")
            body = email.get("body", {}).get("content", "") or email.get("bodyPreview", "")
            tasks = processor.extract_tasks_from_email(body, subject)
            all_extracted_tasks.extend(tasks)
            progress_components.append(text(f"Email {i}: '{subject[:30]}...' → {len(tasks)} tasks", variant="body"))

        progress_components.append(alert(f"Total tasks extracted: {len(all_extracted_tasks)}", variant="info"))

        progress_components.append(divider())
        progress_components.append(text("Step 3: Checking existing To Do tasks...", variant="subtitle"))

        existing_tasks = client.get_todo_tasks()
        progress_components.append(alert(f"Found {len(existing_tasks)} existing active tasks", variant="info"))

        progress_components.append(divider())
        progress_components.append(text("Step 4: Deduplicating and creating new tasks...", variant="subtitle"))

        new_tasks_created = []
        duplicate_tasks = []

        for task in all_extracted_tasks:
            if deduplicator.is_duplicate(task, existing_tasks):
                duplicate_tasks.append(task)
                progress_components.append(text(f"Duplicate skipped: '{task.get('title', '')[:40]}...'", variant="caption"))
            else:
                notes = f"Extracted from email. Details: {task.get('description', '')}"
                if task.get('deadline'):
                    notes += f"\nDeadline: {task.get('deadline')}"

                created_task = client.create_todo_task(
                    title=task.get('title', 'New Task'),
                    notes=notes
                )

                if created_task:
                    new_tasks_created.append(task)
                    progress_components.append(text(f"Created: '{task.get('title', '')[:40]}...'", variant="body"))
                else:
                    progress_components.append(text(f"Failed to create: '{task.get('title', '')[:40]}...'", variant="caption"))

        summary_row = row([
            metric_card("Emails Processed", str(min(5, len(emails)))),
            metric_card("Tasks Extracted", str(len(all_extracted_tasks))),
            metric_card("Duplicates Found", str(len(duplicate_tasks))),
            metric_card("New Tasks Created", str(len(new_tasks_created)), variant="success" if new_tasks_created else "default")
        ])

        components = [
            card("Inbox Triage Results", [
                summary_row,
                divider(),
                column(progress_components)
            ])
        ]

        if new_tasks_created:
            new_task_rows = []
            for i, task in enumerate(new_tasks_created, 1):
                new_task_rows.append([
                    str(i),
                    task.get('title', '')[:50],
                    task.get('priority', 'medium').capitalize(),
                    task.get('deadline', 'Not specified')
                ])

            components.append(
                card("New Tasks Added to To Do", [
                    table(["#", "Title", "Priority", "Deadline"], new_task_rows)
                ])
            )

        if duplicate_tasks:
            duplicate_task_rows = []
            for i, task in enumerate(duplicate_tasks[:5], 1):
                duplicate_task_rows.append([
                    str(i),
                    task.get('title', '')[:50],
                    "Already exists in To Do"
                ])

            components.append(
                card("Duplicate Tasks (Not Added)", [
                    table(["#", "Title", "Reason"], duplicate_task_rows)
                ])
            )

        return create_response(components, data={
            "emails_processed": len(emails[:5]),
            "tasks_extracted": len(all_extracted_tasks),
            "duplicates_found": len(duplicate_tasks),
            "new_tasks_created": len(new_tasks_created),
            "new_tasks": new_tasks_created,
            "duplicate_tasks": duplicate_tasks,
            "triage_date": datetime.now().isoformat()
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to triage inbox: {str(e)}", variant="error")
        )

def get_inbox_todo_items(days: int = 7, email_limit: int = 10, **kwargs) -> Dict[str, Any]:
    """Analyze inbox emails and return a list of actionable todo items found."""
    try:
        if requests is None:
            return create_response(
                alert("The 'requests' package is required. Please install it: pip install requests", variant="error")
            )

        credentials = kwargs.get("_credentials", {})
        client = GraphAPIClient(credentials)
        processor = LLMProcessor()

        emails = client.get_recent_emails(days=days, top=email_limit)

        if not emails:
            return create_response(
                alert(f"No emails found from the past {days} days.", variant="info")
            )

        all_tasks = []
        email_task_map = {}

        for email in emails[:email_limit]:
            subject = email.get("subject", "No Subject")
            body = email.get("body", {}).get("content", "") or email.get("bodyPreview", "")
            tasks = processor.extract_tasks_from_email(body, subject)

            if tasks:
                for task in tasks:
                    task["source_email"] = subject
                    task["email_link"] = email.get("webLink", "")
                    all_tasks.append(task)
                email_task_map[subject] = len(tasks)

        if not all_tasks:
            return create_response(
                card("Inbox Todo Analysis", [
                    metric_card("No Tasks Found", "0", subtitle=f"Analyzed {min(email_limit, len(emails))} emails"),
                    alert("No actionable todo items were found in the analyzed emails.", variant="info"),
                    text(f"Scanned {min(email_limit, len(emails))} emails from the past {days} days.", variant="caption")
                ])
            )

        task_rows = []
        for i, task in enumerate(all_tasks, 1):
            title = task.get("title", "Untitled")
            description = task.get("description", "")
            priority = task.get("priority", "medium").capitalize()
            deadline = task.get("deadline", "Not specified")
            source = task.get("source_email", "")[:40] + ("..." if len(task.get("source_email", "")) > 40 else "")

            task_rows.append([
                str(i),
                title[:60] + ("..." if len(title) > 60 else ""),
                description[:50] + ("..." if len(description) > 50 else ""),
                priority,
                deadline,
                source
            ])

        email_summary_rows = []
        for subject, count in list(email_task_map.items())[:5]:
            email_summary_rows.append([
                subject[:50] + ("..." if len(subject) > 50 else ""),
                str(count)
            ])

        components = [
            card("Inbox Todo Items Analysis", [
                row([
                    metric_card("Emails Analyzed", str(min(email_limit, len(emails))), subtitle=f"Past {days} days"),
                    metric_card("Tasks Found", str(len(all_tasks)), subtitle="Actionable items"),
                    metric_card("Emails with Tasks", str(len(email_task_map)), subtitle="Containing actionable items")
                ]),
                divider(),
                card("Extracted Todo Items", [
                    table(["#", "Title", "Description", "Priority", "Deadline", "Source Email"], task_rows),
                    text(f"Showing {len(all_tasks)} actionable items found in emails.", variant="caption")
                ])
            ])
        ]

        if email_summary_rows:
            components.append(
                card("Email Task Summary", [
                    table(["Email Subject", "Tasks Found"], email_summary_rows),
                    text(f"Top {len(email_summary_rows)} emails with the most tasks.", variant="caption")
                ])
            )

        priority_counts = {"High": 0, "Medium": 0, "Low": 0}
        for task in all_tasks:
            priority = task.get("priority", "medium").capitalize()
            if priority in priority_counts:
                priority_counts[priority] += 1

        components.append(
            card("Task Priority Distribution", [
                row([
                    metric_card("High Priority", str(priority_counts["High"]),
                                variant="error" if priority_counts["High"] > 0 else "default"),
                    metric_card("Medium Priority", str(priority_counts["Medium"]), variant="warning"),
                    metric_card("Low Priority", str(priority_counts["Low"]), variant="success")
                ])
            ])
        )

        return create_response(components, data={
            "total_emails_analyzed": min(email_limit, len(emails)),
            "total_tasks_found": len(all_tasks),
            "tasks": all_tasks,
            "email_task_map": email_task_map,
            "priority_distribution": priority_counts,
            "analysis_date": datetime.now().isoformat()
        })
    except Exception as e:
        return create_response(
            alert(f"Failed to analyze inbox for todo items: {str(e)}", variant="error")
        )

TOOL_REGISTRY = {
    "get_auth_status": {
        "function": get_auth_status,
        "description": "Check Microsoft Graph authentication status and display connection information",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "scope": "tools:read"
    },
    "fetch_recent_emails": {
        "function": fetch_recent_emails,
        "description": "Fetch recent emails from Outlook inbox with optional filtering by days and limit",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back for emails",
                    "default": 7
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of emails to fetch",
                    "default": 20
                }
            },
            "required": []
        },
        "scope": "tools:search"
    },
    "analyze_email_for_tasks": {
        "function": analyze_email_for_tasks,
        "description": "Analyze a specific email or the latest email to extract actionable tasks using LLM",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "Email ID to analyze, or 'latest' for most recent email",
                    "default": "latest"
                }
            },
            "required": []
        },
        "scope": "tools:read"
    },
    "get_current_todo_tasks": {
        "function": get_current_todo_tasks,
        "description": "Fetch current active tasks from Microsoft To Do",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "description": "Name of the To Do list to fetch tasks from",
                    "default": "Tasks"
                }
            },
            "required": []
        },
        "scope": "tools:search"
    },
    "triage_inbox_automated": {
        "function": triage_inbox_automated,
        "description": "Automated inbox triage: fetch emails, extract tasks, deduplicate, and add to To Do",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of emails to process",
                    "default": 7
                },
                "email_limit": {
                    "type": "integer",
                    "description": "Maximum number of emails to analyze",
                    "default": 10
                }
            },
            "required": []
        },
        "scope": "tools:write"
    },
    "get_inbox_todo_items": {
        "function": get_inbox_todo_items,
        "description": "Analyze inbox emails and return a list of actionable todo items found",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back for emails",
                    "default": 7
                },
                "email_limit": {
                    "type": "integer",
                    "description": "Maximum number of emails to analyze",
                    "default": 10
                }
            },
            "required": []
        },
        "scope": "tools:search"
    }
}