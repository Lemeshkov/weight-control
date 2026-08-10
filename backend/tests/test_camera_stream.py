import asyncio

from routers.camera import camera_mjpeg_frames, stream_camera


class LatestFrameClient:
    def __init__(self, sequence, data):
        self.publish(sequence, data)

    def publish(self, sequence, data):
        self.frame = {
            "sequence_number": sequence,
            "data": data,
            "size": len(data),
        }

    def get_frame(self):
        return dict(self.frame)


def test_one_mjpeg_consumer_receives_new_frame_sequence():
    async def scenario():
        client = LatestFrameClient(1, b"jpeg-A")
        stream = camera_mjpeg_frames(client, poll_interval=0)
        first = await anext(stream)
        client.publish(2, b"jpeg-B")
        second = await anext(stream)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(scenario())

    assert b"--frame\r\n" in first
    assert b"Content-Type: image/jpeg\r\n" in first
    assert b"Content-Length: 6\r\n" in first
    assert first.endswith(b"jpeg-A\r\n")
    assert second.endswith(b"jpeg-B\r\n")
    assert first != second


def test_mjpeg_consumer_does_not_repeat_same_sequence():
    async def scenario():
        client = LatestFrameClient(1, b"jpeg-A")
        stream = camera_mjpeg_frames(client, poll_interval=0)
        first = await anext(stream)

        async def publish_later():
            await asyncio.sleep(0)
            client.publish(2, b"jpeg-B")

        task = asyncio.create_task(publish_later())
        second = await anext(stream)
        await task
        await stream.aclose()
        return first, second

    first, second = asyncio.run(scenario())
    assert first.endswith(b"jpeg-A\r\n")
    assert second.endswith(b"jpeg-B\r\n")


def test_stream_response_disables_cache_and_proxy_buffering():
    response = asyncio.run(stream_camera())

    assert response.media_type == "multipart/x-mixed-replace; boundary=frame"
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
