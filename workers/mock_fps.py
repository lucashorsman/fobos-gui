import asyncio
import time

class MockPositioner:
    def __init__(self, pid, center=(0.0, 0.0)):
        self.id = pid
        self.alpha = 0.0
        self.beta = 0.0
        self.center = center

class MockFPS:
    def __init__(self, num_positioners=5):
        self.positioners = {}
        # Create dummy positioners in a grid layout
        cols = int(num_positioners ** 0.5) or 1
        pitch = 280.0
        for i in range(1, num_positioners + 1):
            row = (i - 1) // cols
            col = (i - 1) % cols
            # Center the grid around (0, 0)
            cx = col * pitch - (cols - 1) * pitch / 2
            cy = row * pitch - ((num_positioners - 1) // cols) * pitch / 2
            self.positioners[i] = MockPositioner(i, center=(cx, cy))

    async def initialise(self):
        # Simulate network or hardware initialization delay
        await asyncio.sleep(0.5)

    async def update_position(self):
        # In a more advanced mock, we might gradually interpolate alpha/beta over time
        # to simulate physical travel, but for now we'll just let them sit at their
        # current values until goto is called.
        pass

    async def goto(self, targets, relative=False):
        """
        targets is a dict of {positioner_id: (alpha, beta)}
        """
        # Simulate physical travel time
        await asyncio.sleep(1.0)
        
        # Update the positions
        for pid, (alpha, beta) in targets.items():
            if pid in self.positioners:
                if relative:
                    self.positioners[pid].alpha += alpha
                    self.positioners[pid].beta += beta
                else:
                    self.positioners[pid].alpha = alpha
                    self.positioners[pid].beta = beta
        
        return True
