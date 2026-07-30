#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_servicecomb_contract_code.py")
POLICY = SCRIPT.parent.parent / "references" / "servicecomb-contract-policy.json"


class ServiceCombContractPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        target = self.repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def stage(self, *paths: str) -> None:
        subprocess.run(["git", "add", *paths], cwd=self.repo, check=True)

    def check(self, policy: Path = POLICY) -> tuple[int, list[dict[str, object]]]:
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-root",
                str(self.repo),
                "--config",
                str(policy),
                "--staged",
                "--format",
                "json",
            ],
            cwd=self.repo,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode, json.loads(result.stdout)

    def rules(self) -> set[str]:
        _, violations = self.check()
        return {str(item["rule"]) for item in violations}

    def test_springmvc_contract_and_dto_are_blocked(self) -> None:
        self.write(
            "src/main/java/demo/OrderApi.java",
            """
            package demo;
            import org.apache.servicecomb.provider.rest.common.RestSchema;
            import org.springframework.web.bind.annotation.*;
            @RequestMapping("/orders")
            public interface OrderApi {
              @PostMapping Order create(OrderRequest request);
            }
            @RestSchema(schemaId = "orders", schemaInterface = OrderApi.class)
            class OrderController implements OrderApi {
              public Order create(OrderRequest request) { return null; }
            }
            """,
        )
        self.write(
            "src/main/java/demo/OrderRequest.java",
            """package demo;
            public class OrderRequest {
              public Address getAddress() { return null; }
            }
            """,
        )
        self.write(
            "src/main/java/demo/Address.java",
            "package demo; public class Address { private String city; }",
        )
        self.write(
            "src/main/java/demo/Order.java",
            "package demo; public record Order(String id) {}",
        )
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB110", "SCB120", "SCB200"}.issubset(rules))

    def test_generated_schema_interface_implementation_is_allowed(self) -> None:
        self.write(
            "src/main/java/demo/OrderController.java",
            """
            package demo;
            import org.apache.servicecomb.provider.rest.common.RestSchema;
            @RestSchema(schemaId = "orders", schemaInterface = GeneratedOrderApi.class)
            public class OrderController implements GeneratedOrderApi {
              @Override public GeneratedOrder create(GeneratedOrderRequest request) { return null; }
            }
            """,
        )
        self.stage("src")
        returncode, violations = self.check()
        self.assertEqual(0, returncode)
        self.assertEqual([], violations)

    def test_jaxrs_contract_and_bean_param_dto_are_blocked(self) -> None:
        self.write(
            "src/main/java/demo/HelloApi.java",
            """
            package demo;
            import org.apache.servicecomb.provider.rest.common.RestSchema;
            import jakarta.ws.rs.*;
            @Path("/hello")
            public interface HelloApi {
              @GET Person hello(@BeanParam Person request);
            }
            @RestSchema(schemaId = "hello", schemaInterface = HelloApi.class)
            class HelloController implements HelloApi {
              public Person hello(Person request) { return null; }
            }
            """,
        )
        self.write(
            "src/main/java/demo/Person.java",
            "package demo; public class Person { @QueryParam(\"name\") private String name; }",
        )
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB110", "SCB120", "SCB200"}.issubset(rules))

    def test_direct_provider_without_schema_interface_is_blocked(self) -> None:
        self.write(
            "src/main/java/demo/LegacyProvider.java",
            """
            package demo;
            import org.apache.servicecomb.provider.rest.common.RestSchema;
            import javax.ws.rs.*;
            @RestSchema(schemaId = "legacy")
            @Path("/legacy")
            public class LegacyProvider {
              @GET public Person get() { return null; }
            }
            """,
        )
        self.write(
            "src/main/java/demo/Person.java",
            "package demo; public class Person { private String name; }",
        )
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB101", "SCB110", "SCB200"}.issubset(rules))

    def test_transparent_rpc_handwritten_interface_is_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Hello.java",
            "package demo; public interface Hello { Person sayHello(Person person); }",
        )
        self.write(
            "src/main/java/demo/HelloImpl.java",
            """
            package demo;
            import org.apache.servicecomb.provider.pojo.RpcSchema;
            @RpcSchema(schemaId = "hello", schemaInterface = Hello.class)
            public class HelloImpl implements Hello {
              public Person sayHello(Person person) { return person; }
            }
            """,
        )
        self.write(
            "src/main/java/demo/Person.java",
            "package demo; public class Person { private String name; }",
        )
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB102", "SCB120", "SCB200"}.issubset(rules))

    def test_swagger_contract_metadata_is_blocked(self) -> None:
        self.write(
            "src/main/java/demo/HelloApi.java",
            """
            package demo;
            import org.apache.servicecomb.provider.rest.common.RestSchema;
            import io.swagger.v3.oas.annotations.*;
            @OpenAPIDefinition
            public interface HelloApi {
              @Operation(operationId = "sayHello") Result sayHello(Input input);
            }
            @RestSchema(schemaId = "hello", schemaInterface = HelloApi.class)
            class HelloController implements HelloApi {
              public Result sayHello(Input input) { return null; }
            }
            """,
        )
        self.write("src/main/java/demo/Input.java", "package demo; public record Input(String name) {}")
        self.write("src/main/java/demo/Result.java", "package demo; public record Result(String value) {}")
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB111", "SCB120", "SCB200"}.issubset(rules))

    def test_restoperations_consumer_and_dto_are_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Consumer.java",
            """
            package demo;
            import org.apache.servicecomb.provider.pojo.RpcReference;
            public class Consumer {
              void call() {
                Person person = new Person();
                RestTemplateBuilder.create().postForObject(
                  "servicecomb://orders/orders", person, Result.class);
              }
            }
            """,
        )
        self.write("src/main/java/demo/Person.java", "package demo; public class Person { private String name; }")
        self.write("src/main/java/demo/Result.java", "package demo; public class Result { private String id; }")
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB130", "SCB200"}.issubset(rules))

    def test_rpc_consumer_handwritten_interface_and_dto_are_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Hello.java",
            "package demo; public interface Hello { Person sayHello(Person input); }",
        )
        self.write("src/main/java/demo/Person.java", "package demo; public class Person { private String name; }")
        self.write(
            "src/main/java/demo/Consumer.java",
            """
            package demo;
            import org.apache.servicecomb.provider.pojo.RpcReference;
            public class Consumer {
              @RpcReference(microserviceName = "hello", schemaId = "hello")
              private Hello hello;
            }
            """,
        )
        self.stage("src")
        rules = self.rules()
        self.assertTrue({"SCB120", "SCB131", "SCB200"}.issubset(rules))

    def test_dto_only_staged_change_is_found_from_existing_contract(self) -> None:
        self.write(
            "src/main/java/demo/Hello.java",
            "package demo; public interface Hello { Person sayHello(Person input); }",
        )
        self.write(
            "src/main/java/demo/Consumer.java",
            """package demo;
            import org.apache.servicecomb.provider.pojo.RpcReference;
            public class Consumer { @RpcReference private Hello hello; }
            """,
        )
        self.write("src/main/java/demo/Person.java", "package demo; public class Person { private String name; }")
        self.stage("src")
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base"],
            cwd=self.repo,
            check=True,
        )
        self.write(
            "src/main/java/demo/Person.java",
            "package demo; public class Person { private String name; private Address address; }",
        )
        self.write("src/main/java/demo/Address.java", "package demo; public record Address(String city) {}")
        self.stage("src/main/java/demo/Person.java", "src/main/java/demo/Address.java")
        rules = self.rules()
        self.assertIn("SCB200", rules)

    def test_tracked_generated_source_is_blocked(self) -> None:
        self.write(
            "target/generated-sources/swagger/demo/GeneratedApi.java",
            "package demo; public interface GeneratedApi {}",
        )
        self.stage("-f", "target/generated-sources/swagger/demo/GeneratedApi.java")
        self.assertIn("SCB000", self.rules())

    def test_reserved_generated_dto_package_is_blocked_without_tracked_interface(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        policy["reserved_contract_type_globs"] = ["demo.contract.model.*"]
        custom_policy = self.repo / "policy.json"
        custom_policy.write_text(json.dumps(policy), encoding="utf-8")
        self.write(
            "src/main/java/demo/contract/model/CreateOrderRequest.java",
            "package demo.contract.model; public class CreateOrderRequest {}",
        )
        self.stage("src")
        _, violations = self.check(custom_policy)
        self.assertIn("SCB001", {str(item["rule"]) for item in violations})

    def test_rpc_reference_method_injection_is_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Hello.java",
            "package demo; public interface Hello { String sayHello(String input); }",
        )
        self.write(
            "src/main/java/demo/Consumer.java",
            """
            package demo;
            import org.apache.servicecomb.provider.pojo.RpcReference;
            public class Consumer {
              @RpcReference(microserviceName = "hello")
              public void setHello(Hello hello) {}
            }
            """,
        )
        self.stage("src")
        self.assertIn("SCB131", self.rules())

    def test_invoker_proxy_handwritten_interface_is_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Hello.java",
            "package demo; public interface Hello { String sayHello(String input); }",
        )
        self.write(
            "src/main/java/demo/Consumer.java",
            """
            package demo;
            import org.apache.servicecomb.provider.pojo.Invoker;
            public class Consumer {
              private Hello hello = Invoker.createProxy("hello", "hello", Hello.class);
            }
            """,
        )
        self.stage("src")
        self.assertIn("SCB131", self.rules())

    def test_unrelated_simple_name_annotations_are_not_blocked(self) -> None:
        self.write(
            "src/main/java/demo/Unrelated.java",
            """
            package demo;
            @RestSchema
            @Path("not-servicecomb")
            public class Unrelated {}
            """,
        )
        self.stage("src")
        returncode, violations = self.check()
        self.assertEqual(0, returncode)
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
