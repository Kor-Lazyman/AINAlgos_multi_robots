"""Publish just the latest completed layer in a separate TensorBoard run."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from torch.utils.tensorboard import SummaryWriter
from tools.smoke_gantt import chart


class LatestGantt:
    def __init__(self, output):
        self.output = Path(output)
        self.artifact = self.output / 'latest_gantt'
        self.artifact.mkdir(parents=True, exist_ok=True)
        self.logdir = self.output / 'tensorboard' / 'latest_gantt'

    def publish(self, rows, *, step, scenario, layer):
        title = f'Latest completed layer | step {step} | {scenario} | layer {layer}'
        chart(self.artifact, rows, title)
        with Image.open(self.artifact / 'gantt.png') as source:
            pixels = np.array(source.convert('RGB'))
        # A separate run isolates the purge from PPO scalar history. Restart
        # this image run at step 0, so TensorBoard retains only its newest image.
        with SummaryWriter(str(self.logdir), purge_step=0) as writer:
            writer.add_image('latest_gantt', pixels, global_step=0, dataformats='HWC')
            writer.flush()
        metadata = dict(training_step=int(step), scenario=str(scenario), layer=int(layer),
                        makespan_s=max(own[-1][0] for own in rows),
                        tensorboard_run='latest_gantt', tensorboard_tag='latest_gantt',
                        tensorboard_image_step=0)
        (self.artifact / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
