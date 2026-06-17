import asyncio
import time

class MockPositioner:
    def __init__(self, pid):
        self.id = pid
        self.alpha = 0.0
        self.beta = 0.0

class MockFPS:
    def __init__(self, num_positioners=1600):
        # Create dummy positioners (IDs 1 through num_positioners)
        self.positioners = {i: MockPositioner(i) for i in range(1, num_positioners + 1)}

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
