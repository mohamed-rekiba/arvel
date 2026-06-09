---
title: API Reference
description: The public Arvel API — every symbol exported from the top-level `arvel` package, rendered from source docstrings and type signatures.
---

# API Reference

This page documents the public surface of the top-level `arvel` package — every
symbol in `arvel.__all__`. It's generated from the installed package's
docstrings and type signatures, so it always matches the version you have.

> [!NOTE]
> Anything **not** listed here is internal and may change without a major
> version bump. Import from `arvel` (e.g. `from arvel import Route`), not from
> deep submodules, unless a guide tells you otherwise.

## Application & lifecycle

::: arvel.Application
::: arvel.ApplicationBuilder
::: arvel.serve
::: arvel.BootError
::: arvel.ShutdownError
::: arvel.ASGIApp
::: arvel.HttpLifespan

## Service container & dependency injection

::: arvel.Container
::: arvel.Scope
::: arvel.dep
::: arvel.AsyncBindingError
::: arvel.BindingResolutionError
::: arvel.CircularDependencyError

## Configuration & environment

::: arvel.config
::: arvel.env
::: arvel.NoPrefix
::: arvel.ConfigError
::: arvel.ConfigNotRegisteredError

## Routing

::: arvel.Route
::: arvel.Router
::: arvel.URL
::: arvel.url
::: arvel.RouteServiceProvider
::: arvel.RoutingError

## HTTP — controllers, requests & resources

::: arvel.Controller
::: arvel.FormRequest
::: arvel.JsonResource
::: arvel.ResourceCollection
::: arvel.wants_json

## HTTP — middleware

::: arvel.Middleware
::: arvel.Authenticate
::: arvel.Cors
::: arvel.Throttle
::: arvel.VerifyCsrf

## HTTP — authentication & rate limiting

::: arvel.Guard
::: arvel.JwtGuard
::: arvel.SessionGuard
::: arvel.UserResolver
::: arvel.Attempt
::: arvel.RateLimiterStore
::: arvel.InMemoryStore
::: arvel.RedisStore

## HTTP — exceptions

::: arvel.HttpException
::: arvel.HttpExceptionHandler
::: arvel.AuthorizationException
::: arvel.BadRequestException
::: arvel.ConflictException
::: arvel.MethodNotAllowedException
::: arvel.NotFoundException
::: arvel.ServerErrorException
::: arvel.ThrottleException
::: arvel.UnauthenticatedException
::: arvel.ValidationException

## Service providers

::: arvel.ServiceProvider
::: arvel.HttpServiceProvider

## Support helpers

::: arvel.Arr
::: arvel.Str
