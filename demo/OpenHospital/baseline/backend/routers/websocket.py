"""WebSocket routes for real-time event streaming."""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from ..services import ws_manager, get_event_store
from ..config import settings

router = APIRouter(tags=["websocket"])


async def redis_listener() -> None:
    """
    后台任务：监听 Redis Pub/Sub 消息并广播到 WebSocket 客户端。

    同时将事件同步到 EventStore 内存存储。
    """
    store = get_event_store()
    simulation_started = False
    redis_client = None
    pubsub = None

    try:
        redis_client = aioredis.from_url(
            f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
            decode_responses=True
        )
        pubsub = redis_client.pubsub()
        await pubsub.psubscribe("sim_events:*")

        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message and message.get("type") == "pmessage":
                    data = message.get("data", "")
                    channel = message.get("channel", "")
                    try:
                        event = json.loads(data) if isinstance(data, str) else data

                        if not simulation_started:
                            store.set_simulation_running(True)
                            simulation_started = True
                        store.process_event(event)
                        await ws_manager.broadcast({
                            "type": "event",
                            "channel": channel,
                            "data": event,
                        })

                    except json.JSONDecodeError:
                        await ws_manager.broadcast({
                            "type": "raw",
                            "channel": channel,
                            "data": data,
                        })

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in redis listener: {e}")
                await asyncio.sleep(1)

    except Exception as e:
        print(f"Redis listener failed: {e}")
    finally:
        if simulation_started:
            store.set_simulation_running(False)
        if pubsub:
            try:
                await pubsub.punsubscribe("sim_events:*")
                await pubsub.close()
            except:
                pass
        if redis_client:
            try:
                await redis_client.close()
            except:
                pass


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket 端点，用于实时事件推送。
    
    客户端连接后会收到所有 Redis Pub/Sub 的事件。
    """
    await ws_manager.connect(websocket)
    
    store = get_event_store()
    
    try:
        await websocket.send_json({
            "type": "connected",
            "status": store.get_simulation_status(),
        })
        
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                
                try:
                    message = json.loads(data)
                    msg_type = message.get("type", "")
                    
                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "get_status":
                        await websocket.send_json({
                            "type": "status",
                            "data": store.get_simulation_status(),
                        })
                    elif msg_type == "get_agents":
                        await websocket.send_json({
                            "type": "agents",
                            "doctors": store.get_doctors(),
                            "patients": store.get_patients(),
                        })
                        
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        ws_manager.disconnect(websocket)


@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket 端点别名，用于实时事件推送。
    """
    await websocket_endpoint(websocket)


@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    agent_id: str,
) -> None:
    """
    WebSocket 端点，用于接收特定 agent 相关的事件。
    """
    await ws_manager.connect(websocket)
    
    store = get_event_store()
    
    try:
        agent = store.get_agent(agent_id)
        if agent:
            await websocket.send_json({
                "type": "agent_info",
                "agent": agent,
            })
        
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                
                try:
                    message = json.loads(data)
                    msg_type = message.get("type", "")
                    
                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "get_messages":
                        messages = store.get_messages(agent_id)
                        await websocket.send_json({
                            "type": "messages",
                            "data": messages,
                        })
                        
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Agent WebSocket error: {e}")
    finally:
        ws_manager.disconnect(websocket)
