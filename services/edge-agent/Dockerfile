FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /edge-agent .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /edge-agent /edge-agent
ENTRYPOINT ["/edge-agent"]
