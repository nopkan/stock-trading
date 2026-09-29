"""Explicit disabled boundary pending approved InnovestX equity API setup."""


class InnovestXBroker:
    name='innovestx'
    live_enabled=False

    def submit_order(self, *args, **kwargs):
        raise RuntimeError('InnovestX live order submission is not implemented; use approved equity API documentation before integration')

    def cancel_order(self, *args, **kwargs):
        raise RuntimeError('InnovestX live order cancellation is not implemented')
