"""Start one loopback server and open the browser only once it is listening."""
import webbrowser
import uvicorn


def run_web(section='', open_browser=True):
    url = 'http://127.0.0.1:8000/' + ('#' + section if section else '')

    class DashboardServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                print(f'Oracle is ready: {url}\nPress Ctrl+C here to stop Oracle.')
                if open_browser:
                    webbrowser.open(url)

    # Disable access logs so Google OAuth callback codes are not written to logs.
    config = uvicorn.Config('app.main:app', host='127.0.0.1', port=8000, access_log=False)
    try:
        DashboardServer(config).run()
    except (OSError, SystemExit):
        print('Oracle could not start. Check whether port 8000 is already in use; stop that server and retry.')
        return 1
    return 0
