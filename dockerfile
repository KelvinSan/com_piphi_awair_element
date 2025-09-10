FROM python:3.12-slim

RUN mkdir /integration

COPY requirements.txt ./integration/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /integration/requirements.txt

RUN ls

COPY ./ /integration

WORKDIR /integration

EXPOSE 3665

CMD ["fastapi", "run", "/integration/src/com_piphi_await_element/app.py", "--port", "3665"]